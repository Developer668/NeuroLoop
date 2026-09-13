"""Outcome telemetry derived from persisted records, never inferred audience outcomes."""
from collections import Counter
import math
from sqlalchemy import select
from .db import Run, Job, Trace, Creative, Decision, Feedback, NotebookEvidence, Asset, Intervention
from .domain import digest, now

TABLE_NAMES = ('runs', 'attempts', 'stages', 'funnel', 'quality_samples', 'failures', 'stop_reasons',
               'readiness', 'readiness_stages', 'candidate_evidence', 'decision_gates',
               'events', 'trace_log', 'capabilities', 'artifact_delivery', 'model_receipts')


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def percentile(values, fraction):
    values = sorted(v for v in values if number(v) is not None)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    low = int(position)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)


def usage_summary(output):
    output = output or {}
    receipt = output.get("vision_receipt") or {}
    model = output.get("model") or receipt.get("model")
    usage = output.get("usage") or receipt.get("usage") or {}
    fields = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens")
    values = {k: v for k in fields if number(v := usage.get(k)) is not None and v >= 0}
    details = usage.get("prompt_tokens_details") or {}
    if number(details.get("cached_tokens")) is not None:
        values["cached_tokens"] = details["cached_tokens"]
    return {model: {**values, "requests": 1}} if isinstance(model, str) and values else {}


def trace_summary(data):
    """Weave-native token usage plus a bounded numeric metrics namespace."""
    output = data.get("output") or {}
    metrics = {"schema_version": "outcome-v1", "cost_known": number(output.get("cost_usd")) is not None}
    for key in ("cost_usd", "gpu_seconds", "confidence", "response_delta"):
        if number(output.get(key)) is not None:
            metrics[key] = output[key]
    for key in ("creative_quality", "brief_alignment", "text_integrity"):
        score = (output.get("scores") or {}).get(key)
        value = score.get("value") if isinstance(score, dict) else score
        if number(value) is not None:
            metrics[key] = value
    if output.get("error_code"):
        metrics["error_code"] = output["error_code"]
    result = {"neuroloop": metrics}
    usage = usage_summary(output)
    if usage:
        result["usage"] = usage
    return result


def snapshot(store):
    with store.read() as session:
        runs = list(session.scalars(select(Run).order_by(Run.created_at)))
        jobs = list(session.scalars(select(Job).order_by(Job.created_at)))
        traces = list(session.scalars(select(Trace).order_by(Trace.started_at)))
        creatives = list(session.scalars(select(Creative)))
        decisions = list(session.scalars(select(Decision)))
        feedback = list(session.scalars(select(Feedback)))
        evidence = list(session.scalars(select(NotebookEvidence).order_by(NotebookEvidence.created_at)))
        assets = {a.id: a for a in session.scalars(select(Asset))}
        interventions = list(session.scalars(select(Intervention)))
        attempts = [t for t in traces if t.inputs.get("job_id") and not t.name.startswith("neuroloop.event.")]
        attempt_rows = []
        for trace in attempts:
            output = trace.output or {}
            usage = usage_summary(output)
            tokens = next(iter(usage.values()), {})
            attempt_rows.append({"trace_id": trace.id, "run_id": trace.run_id, "job_id": trace.inputs.get("job_id"),
                "stage": trace.name.removeprefix("neuroloop."), "attempt": trace.inputs.get("attempt"),
                "started_at": trace.started_at, "ended_at": trace.ended_at,
                "latency_seconds": max(0, trace.ended_at - trace.started_at) if trace.ended_at is not None else None,
                "status": "FAILED" if trace.exception else output.get("status", "RUNNING"),
                "error_code": output.get("error_code") or trace.exception,
                "model": output.get("model"), "cost_usd": number(output.get("cost_usd")),
                "prompt_tokens": tokens.get("prompt_tokens"), "completion_tokens": tokens.get("completion_tokens"),
                "total_tokens": tokens.get("total_tokens"), "cached_tokens": tokens.get("cached_tokens"),
                "weave_url": trace.url, "delivery": trace.status})
        stage_rows = []
        for stage in sorted({a["stage"] for a in attempt_rows}):
            rows = [a for a in attempt_rows if a["stage"] == stage]
            latencies = [a["latency_seconds"] for a in rows if a["latency_seconds"] is not None]
            stage_rows.append({"stage": stage, "attempts": len(rows), "succeeded": sum(a["status"] == "SUCCEEDED" for a in rows),
                "failed": sum(a["status"] == "FAILED" for a in rows), "latency_samples": len(latencies),
                "median_seconds": percentile(latencies, .5), "p95_seconds": percentile(latencies, .95)})
        run_rows = []
        for run in runs:
            rjobs = [j for j in jobs if j.run_id == run.id]
            generated = [c for c in creatives if c.run_id == run.id and c.output_asset_id]
            rdecisions = [d for d in decisions if d.run_id == run.id]
            rfeedback = [f for f in feedback if any(c.id == f.creative_id for c in generated)]
            accepted = {f.creative_id for f in rfeedback if f.kind in ("accept", "accept_after_edit")}
            decision_at = min((d.created_at for d in rdecisions), default=None)
            approved = any(j.kind == "REVIEW_PLAN" and j.status == "SUCCEEDED" and (j.result or {}).get("choice") == "APPROVE"
                and (j.result or {}).get("confidence", 0) >= run.snapshot.get("config", {}).get("decision_confidence_floor", .7) for j in rjobs)
            run_rows.append({"run_id": run.id, "created_at": run.created_at, "state": run.state, "stop_reason": run.stop_reason,
                "plan_approved": approved, "generated_candidates": len(generated), "decisions": len(rdecisions),
                "full_loop_completed": bool(generated and rdecisions), "accepted_creatives": len(accepted),
                "time_to_decision_seconds": max(0, decision_at - run.created_at) if decision_at is not None else None,
                "model_calls": sum(j.attempt for j in rjobs), "round": run.round,
                "selected_creative_id": run.champion_id})
        # Standalone imported evaluations are explicitly separate from campaign completion.
        quality_rows = []
        for row in evidence:
            if row.evaluator != "vision":
                continue
            result, asset = row.result, assets[row.input_asset_id]
            provenance = result.get("provenance", {})
            score = result.get("scores", {}).get("creative_quality", {})
            quality_rows.append({"evidence_id": row.id, "asset_id": row.input_asset_id, "media_kind": asset.kind,
                "source": "operator_notebook_evaluation", "created_at": row.created_at,
                "evaluator": provenance.get("model"), "cohort": row.comparison_key,
                "quality": number(score.get("value")) if isinstance(score, dict) else None,
                "configuration_hash": provenance.get("configuration_hash"),
                "constraints": dict(Counter(c.get("status", "UNKNOWN") for c in result.get("constraints", [])))})
        completed_jobs = [j for j in jobs if j.status in ("SUCCEEDED", "FAILED", "CANCELLED", "UNCERTAIN")]
        first = [a for a in attempt_rows if a["attempt"] == 1 and a["ended_at"] is not None]
        accepted_count = sum(r["accepted_creatives"] for r in run_rows)
        known_costs = [a["cost_usd"] for a in attempt_rows if a["cost_usd"] is not None]
        blocked = [r for r in run_rows if r["state"] in ("NEEDS_ATTENTION", "READY_FOR_REVIEW") and r["stop_reason"]]
        missing = [r for r in blocked if any(k in r["stop_reason"] for k in ("UNAVAILABLE", "MISSING", "INSUFFICIENT_EVIDENCE", "CAPABILITY"))]
        gains = {}
        for item in interventions:
            observation = item.observation
            current, parent = observation.get("quality") or {}, observation.get("parent_quality") or {}
            if observation.get("selected") and number(current.get("value")) is not None and number(parent.get("value")) is not None:
                creative = next(c for c in creatives if c.id == item.creative_id)
                key = (item.run_id, creative.round, item.context_key)
                gains[key] = max(gains.get(key, float("-inf")), current["value"] - parent["value"])
        rate = lambda n, d: n / d if d else None
        metrics = {"optimization_runs_started": len(runs), "full_loop_completion_rate": rate(sum(r["full_loop_completed"] for r in run_rows), len(runs)),
            "human_acceptance_rate": rate(accepted_count, len(runs)), "accepted_creatives": accepted_count,
            "median_time_to_decision_seconds": percentile([r["time_to_decision_seconds"] for r in run_rows], .5),
            "p95_attempt_latency_seconds": percentile([a["latency_seconds"] for a in attempt_rows], .95),
            "first_attempt_success_rate": rate(sum(a["status"] == "SUCCEEDED" for a in first), len(first)),
            "eventual_job_success_rate": rate(sum(j.status == "SUCCEEDED" for j in completed_jobs), len(completed_jobs)),
            "retry_rate": rate(sum(j.attempt > 1 for j in jobs), len(jobs)),
            "blocked_run_rate": rate(len(blocked), len(runs)), "missing_evidence_or_capability_runs": len(missing),
            "uncertain_jobs": sum(j.status == "UNCERTAIN" for j in jobs), "dead_letter_jobs": sum(j.status == "FAILED" and j.attempt >= j.max_attempts for j in jobs),
            "cancelled_jobs": sum(j.status == "CANCELLED" for j in jobs),
            "quality_gain_per_round": sum(gains.values()) / len(gains) if gains else None,
            "cost_per_accepted_creative_usd": sum(known_costs) / accepted_count if accepted_count and attempt_rows and len(known_costs) == len(attempt_rows) else None,
            "known_attempt_cost_usd": sum(known_costs) if known_costs else None,
            "unknown_cost_attempts": sum(a["cost_usd"] is None for a in attempt_rows),
            "model_attempts": len(attempt_rows), "token_covered_attempts": sum(a["total_tokens"] is not None for a in attempt_rows),
            "recorded_total_tokens": sum(a["total_tokens"] or 0 for a in attempt_rows),
            "weave_delivered": sum(t.status == "DELIVERED" for t in traces), "weave_pending": sum(t.status != "DELIVERED" for t in traces)}
        funnel = [{"stage": name, "completed_runs": count} for name, count in (
            ("Run created", len(runs)), ("Plan approved", sum(r["plan_approved"] for r in run_rows)),
            ("Candidate generated", sum(r["generated_candidates"] > 0 for r in run_rows)),
            ("Decision produced", sum(r["decisions"] > 0 for r in run_rows)), ("Human accepted", sum(r["accepted_creatives"] > 0 for r in run_rows)))]
        from .readiness_telemetry import readiness
        verification = readiness(session, store, runs, jobs, creatives, decisions, assets)
        from .diagnostic_telemetry import diagnostics
        operational = diagnostics(session, jobs, traces, evidence)
        metrics.update(verification.pop('metrics'))
        data = {"schema_version": "outcome-telemetry-v3", **operational, **verification, "metrics": metrics, "runs": run_rows, "attempts": attempt_rows,
            "stages": stage_rows, "funnel": funnel, "quality_samples": quality_rows,
            "failures": [{"error_code": code, "attempts": count} for code, count in Counter(a["error_code"] for a in attempt_rows if a["error_code"]).items()],
            "stop_reasons": [{"reason": reason, "runs": count} for reason, count in Counter(r["stop_reason"] for r in blocked).items()],
            "notes": ["All counts derive from persisted records. No successful creative or human outcome is synthesized.",
                "Full-loop completion requires a generated campaign candidate and a recorded decision; notebook imports never count.",
                "Full-loop VERIFIED additionally requires approved planning, eligible evaluated evidence and a generated child linked to an applied revision decision. Denominator: runs with attempted jobs.",
                "Required-evidence completion uses the engine's evaluator requirements; eligibility additionally requires its quality and hard-constraint gates. Neither metric proves artifact durability.",
                "Human acceptance counts only explicit accept or accept_after_edit feedback, never likes, locks, or model approval.",
                "Quality samples are separate operator evaluations, grouped by evaluator cohort; no global quality trend is inferred.",
                "Cost is unavailable when the provider supplied no dollar receipt; unknown costs are not zero.",
                "Quality gain per round and cost per acceptance remain unavailable until comparable decision and complete cost evidence exists.",
                "Latency includes completed attempts, including failures; running attempts are excluded. Percentiles use linear interpolation."]}
        return {**data, "snapshot_sha256": digest(data), "generated_at": now()}
