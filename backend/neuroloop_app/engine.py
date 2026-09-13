"""Durable regeneration state machine, independent of any particular model.

Every next action is committed with its predecessor's result. Notebook/model
execution is outside this process, and neither a model nor an MCP client can
approve advertising expenditure.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from typing import Any
import hashlib
import hmac
import secrets
import math
from sqlalchemy import select
from .config import Settings
from .db import (Asset, Campaign, Creative, Decision, Deployment, Evaluation, Event,
                 Feedback, Intervention, Job, NotebookEvidence, PolicyProposal, Run, Store, Trace, Worker, Deployment, record)
from .domain import (CampaignSpec, CandidatePlan, CompleteJob, DecisionResult, DeploymentSpec,
                     EvaluationResult, FailJob, FeedbackRequest, GenerationResult, PlanResult, PlanReview,
                     ResearchProposal, RunConfig, RunState, StartRun, TERMINAL, PAUSED,
                     WorkerHello, ExecutionSummary, ModelProvenance, digest, now, uid)
from .storage import ObjectStore, StorageError, inspect_media, extract_document


class DomainError(ValueError):
    def __init__(self, detail: str, status: int = 409):
        super().__init__(detail)
        self.detail, self.status = detail, status


def required(session, model, identity, lock=False):
    query = select(model).where(model.id == identity)
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise DomainError(f"{model.__tablename__} record not found", 404)
    return row


def emit(session, run, kind, **detail):
    session.add(Event(run_id=run.id, kind=kind, detail=detail))
    run.updated_at = now()
    # Deterministic state transitions are real spans too; keep private content local.
    allowed = {"job_id", "job_type", "creative_id", "worker_id", "attempt", "generation_round", "round", "action", "proposed_action", "confidence", "selected_creative_ids", "code", "outcome", "experiment_id", "review_digest", "evaluator", "feedback_kind", "asset_id", "size", "mime"}
    metadata = {k: v for k, v in detail.items() if k in allowed}
    session.add(Trace(id=uid(), run_id=run.id, parent_id=run.id, name="neuroloop.event."+kind.lower(), inputs=metadata,
                      output={"state": str(run.state)}, started_at=run.updated_at, ended_at=run.updated_at))


def close_trace(session, identity, output, error=None):
    if identity is None:
        return  # A queued job has no execution span yet.
    trace = session.get(Trace, identity)
    if trace:
        trace.output, trace.exception, trace.ended_at = output, error, now()
        trace.revision += 1
        trace.status = "PENDING"


class LoopEngine:
    def __init__(self, store: Store, objects: ObjectStore):
        self.store, self.objects, self.settings = store, objects, store.settings

    def create_campaign(self, spec: CampaignSpec):
        sources = {"brief": spec.brief, "brand.source_text": spec.brand.source_text,
                   "brand.product_description": spec.brand.product_description}
        for claim in spec.brand.approved_claims:
            if claim.source_id not in sources or claim.source_quote not in sources[claim.source_id]:
                raise DomainError("Approved claims require an exact quote from the supplied source", 422)
            if claim.text not in claim.source_quote:
                raise DomainError("Approved claim text must be supported verbatim by its source quote", 422)
        with self.store.transaction() as session:
            campaign = Campaign(id=uid(), spec=spec.model_dump())
            session.add(campaign)
            session.flush()
            return record(campaign)

    def campaigns(self):
        with self.store.read() as session:
            return [record(c) for c in session.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(200))]

    def add_asset(self, campaign_id: str, path: Path, name: str, *, job_id=None, worker_id=None, lease_token=None, upload_key=None):
        if not 0 < path.stat().st_size <= self.settings.max_upload_bytes:
            raise DomainError("File is empty or exceeds the upload limit", 413)
        info = inspect_media(path, self.settings, internal=job_id is not None)
        if info.kind == "document":
            info.details = extract_document(path, info)
        incoming_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        scoped_key = f"{job_id}:{upload_key}" if job_id and upload_key else None
        with self.store.transaction() as session:
            required(session, Campaign, campaign_id)
            if job_id:
                job = required(session, Job, job_id, lock=True)
                self._check_lease(session, job, worker_id, lease_token, allow_uncertain=True)
                run = required(session, Run, job.run_id, lock=True)
                if run.campaign_id != campaign_id:
                    raise DomainError("Cross-campaign upload is forbidden", 403)
                if not upload_key or len(upload_key) > 100:
                    raise DomainError("Worker uploads need a stable upload key", 422)
            if scoped_key:
                existing = session.scalar(select(Asset).where(Asset.upload_key == scoped_key))
                if existing:
                    if existing.sha256 != incoming_sha:
                        raise DomainError("Idempotent upload key was reused with different bytes")
                    return record(existing)
            # Storage is immutable. A storage/database failure can leave an orphan,
            # but never lose or replace a previous candidate's media.
            identity = uid()
            key, sha, size = self.objects.put(path, campaign_id, identity)
            asset = Asset(id=identity, campaign_id=campaign_id, job_id=job_id, upload_key=scoped_key,
                          name=Path(name.replace("\\", "/")).name[:255], kind=info.kind, mime=info.mime,
                          sha256=sha, size=size, object_key=key, details=info.details)
            session.add(asset)
            session.flush()
            return record(asset)

    def asset(self, identity):
        with self.store.read() as session:
            return record(required(session, Asset, identity))

    def start(self, campaign_id: str, request: StartRun, idempotency_key: str):
        if not idempotency_key or len(idempotency_key) > 120:
            raise DomainError("A bounded Idempotency-Key is required", 422)
        scoped_key = f"{campaign_id}:{idempotency_key}"
        request_hash = digest(request.model_dump())
        with self.store.transaction() as session:
            campaign = required(session, Campaign, campaign_id, lock=True)
            old = session.scalar(select(Run).where(Run.idempotency_key == scoped_key))
            if old:
                if old.request_hash != request_hash:
                    raise DomainError("Idempotency-Key reused with different run settings")
                return record(old)
            refs = []
            for identity in dict.fromkeys(request.reference_asset_ids):
                asset = required(session, Asset, identity)
                if asset.campaign_id != campaign_id:
                    raise DomainError("References must belong to the campaign", 403)
                refs.append(identity)
            run = Run(id=uid(), campaign_id=campaign_id, idempotency_key=scoped_key, request_hash=request_hash,
                      state=RunState.PLANNING, round=0, snapshot={"campaign": campaign.spec, "config": request.config.model_dump(),
                      "reference_asset_ids": refs, "policy_version": "core-2026-09-12", "strategy_policy": "bounded-tree-v1"},
                      selected_ids=[], stats={"generation_count": 0, "model_calls": 0, "gpu_seconds": 0,
                      "known_cost_usd": 0, "unknown_cost_jobs": 0, "budget_committed_usd": 0, "plateau": 0, "extra_evaluations": 0})
            session.add(run)
            session.flush()
            session.add(Trace(id=run.id, run_id=run.id, parent_id=None, name="neuroloop.campaign_run",
                              inputs={"campaign_id": campaign_id, "run_id": run.id, "policy_version": "core-2026-09-12"}))
            emit(session, run, "RUN_CREATED", config=request.config.model_dump(), reference_asset_ids=refs)
            self._plan_job(session, run, [])
            return record(run)

    def _enqueue(self, session, run, kind, capability, payload, key, creative_id=None):
        old = session.scalar(select(Job).where(Job.idempotency_key == key))
        if old:
            return old
        job = Job(id=uid(), run_id=run.id, creative_id=creative_id, kind=kind, capability=capability,
                  payload=payload, idempotency_key=key, max_attempts=self.settings.max_job_attempts)
        session.add(job)
        session.flush()
        emit(session, run, "JOB_QUEUED", job_id=job.id, job_type=kind, creative_id=creative_id, capability=capability)
        return job

    def _asset_refs(self, session, ids):
        return [{"asset_id": a.id, "name": a.name, "kind": a.kind, "mime": a.mime, "sha256": a.sha256,
                 "size": a.size, "details": a.details, "download_path": f"/api/v2/assets/{a.id}/content"}
                for a in [required(session, Asset, identity) for identity in ids]]

    def _plan_job(self, session, run, parents, conditioning="media", constraint_repair=False):
        cfg = RunConfig.model_validate(run.snapshot["config"])
        remaining = cfg.max_candidates - run.stats["generation_count"]
        specs = []
        if not parents:
            specs = [{"parent_creative_id": None} for _ in range(min(cfg.initial_candidates, remaining))]
        else:
            for parent in parents[:cfg.beam_width]:
                specs.extend({"parent_creative_id": parent.id} for _ in range(cfg.branch_factor))
            specs = specs[:remaining]
        if not specs:
            self._review(session, run, "CANDIDATE_BUDGET_EXHAUSTED")
            return
        recent_feedback = [record(f) for f in session.scalars(select(Feedback).where(Feedback.campaign_id == run.campaign_id).order_by(Feedback.created_at.desc()).limit(30))]
        prior = [record(i) for i in session.scalars(select(Intervention).where(Intervention.campaign_id == run.campaign_id).order_by(Intervention.created_at.desc()).limit(40))]
        payload = {"snapshot": run.snapshot, "round": run.round, "candidate_slots": specs, "conditioning": conditioning,
                   "references": self._asset_refs(session, run.snapshot["reference_asset_ids"]),
                   "parents": [{"creative": record(p), "asset": self._asset_refs(session, [p.output_asset_id])[0], "evidence": self._evidence(session, p)} for p in parents],
                   "human_feedback": recent_feedback, "intervention_history": prior,
                   "last_decision": run.stats.get("last_decision"),
                   "constraint_repair": constraint_repair}
        capability = "generate_" + run.snapshot["campaign"]["media_kind"]
        payload["generator_contracts"] = [w.capabilities[capability] for w in session.scalars(select(Worker))
            if w.capabilities.get(capability, {}).get("status") == "READY"]
        self._enqueue(session, run, "PLAN", "reasoner", payload, f"{run.id}:plan:{run.round}")
        run.state = RunState.PLANNING if run.round == 0 else RunState.REGENERATING

    def register_worker(self, hello: WorkerHello):
        if hello.provider.lower() == "molab" and not hello.provider_workload_approved:
            raise DomainError("Molab workload approval is required; outbound transport is not a provider-policy exemption", 403)
        allowed = {"reasoner", "typesafe", "summary", "generate_video", "generate_image", "evaluate_vision", "evaluate_tsam", "evaluate_tribe"}
        if set(hello.capabilities) - allowed:
            raise DomainError("Unknown worker capability", 422)
        with self.store.transaction() as session:
            worker = session.get(Worker, hello.worker_id)
            if not worker:
                worker = Worker(id=hello.worker_id)
                session.add(worker)
            worker.capabilities, worker.provider = hello.capabilities, hello.provider
            worker.workload_approved, worker.heartbeat_at = hello.provider_workload_approved, now()
            session.flush()
            return record(worker)

    def _budget_reason(self, run, cfg, *, generation=False):
        if now() - run.created_at >= cfg.max_wall_seconds:
            return "WALL_TIME_BUDGET_EXHAUSTED"
        if run.stats["model_calls"] >= cfg.max_model_calls:
            return "MODEL_CALL_BUDGET_EXHAUSTED"
        if run.stats["gpu_seconds"] >= cfg.max_gpu_seconds:
            return "GPU_TIME_BUDGET_EXHAUSTED"
        if cfg.max_cost_usd is not None and run.stats["known_cost_usd"] >= cfg.max_cost_usd:
            return "COST_BUDGET_EXHAUSTED"
        if generation and run.stats["generation_count"] >= cfg.max_candidates:
            return "CANDIDATE_BUDGET_EXHAUSTED"
        return None

    def claim(self, worker_id):
        self.recover_expired()
        with self.store.transaction() as session:
            if not self.store.sqlite:
                from sqlalchemy import text
                session.execute(text("SELECT pg_advisory_xact_lock(7100912026)"))
            worker = required(session, Worker, worker_id, lock=True)
            worker.heartbeat_at = now()
            # Deliberately one active job across the shared model runtime.
            # This is a safe baseline, not a claim that all weights fit together.
            if session.scalar(select(Job.id).where(Job.status == "LEASED").limit(1)):
                return None
            ready = [k for k, value in worker.capabilities.items() if value.get("status") == "READY"]
            if not ready:
                return None
            jobs = session.scalars(select(Job).where(Job.status.in_(["PENDING", "RETRY"]), Job.available_at <= now(), Job.capability.in_(ready)).order_by(Job.created_at).with_for_update(skip_locked=True)).all()
            for job in jobs:
                run = required(session, Run, job.run_id, lock=True)
                summary_allowed = job.kind == "SUMMARY" and run.state in {RunState.READY_FOR_REVIEW, RunState.COMPLETE}
                if (run.state in TERMINAL or run.state in PAUSED) and not summary_allowed:
                    continue
                cfg = RunConfig.model_validate(run.snapshot["config"])
                reason = self._budget_reason(run, cfg)
                if reason:
                    if job.kind == "SUMMARY":
                        job.status, job.completed_at = "CANCELLED", now()
                        emit(session, run, "SUMMARY_SKIPPED", reason=reason)
                        continue
                    self._review(session, run, reason)
                    self._cancel_pending(session, run)
                    continue
                stats = dict(run.stats)
                reservation = worker.capabilities[job.capability].get("cost_ceiling_usd")
                if cfg.max_cost_usd is not None:
                    if reservation is None and job.kind == "GENERATE":
                        reservation = cfg.generation_cost_reservation_usd
                    if not isinstance(reservation, (int, float)) or isinstance(reservation, bool) or not math.isfinite(reservation) or reservation < 0:
                        if job.kind == "SUMMARY":
                            job.status, job.completed_at = "CANCELLED", now()
                            emit(session, run, "SUMMARY_SKIPPED", reason="MISSING_CONSERVATIVE_COST_QUOTE")
                            continue
                        run.state, run.stop_reason = RunState.NEEDS_ATTENTION, "MISSING_CONSERVATIVE_COST_QUOTE"
                        emit(session, run, "COST_PREFLIGHT_BLOCKED", job_id=job.id)
                        continue
                    if stats["budget_committed_usd"] + reservation > cfg.max_cost_usd:
                        if job.kind == "SUMMARY":
                            job.status, job.completed_at = "CANCELLED", now()
                            emit(session, run, "SUMMARY_SKIPPED", reason="COST_BUDGET_EXHAUSTED")
                            continue
                        self._review(session, run, "COST_BUDGET_EXHAUSTED")
                        self._cancel_pending(session, run)
                        continue
                    stats["budget_committed_usd"] += reservation
                token = secrets.token_urlsafe(32)
                job.status, job.worker_id, job.lease_hash = "LEASED", worker_id, hashlib.sha256(token.encode()).hexdigest()
                job.lease_until, job.started_at, job.attempt = now() + self.settings.lease_seconds, now(), job.attempt + 1
                stats["model_calls"] += 1
                run.stats = stats
                trace_id = job.id if job.attempt == 1 else uid()
                job.progress = {"trace_id": trace_id, "cost_reservation_usd": reservation}
                session.add(Trace(id=trace_id, run_id=run.id, parent_id=run.id, name=f"neuroloop.{job.kind.lower()}",
                                  inputs={"run_id": run.id, "job_id": job.id, "creative_id": job.creative_id, "attempt": job.attempt, "generation_round": run.round}))
                emit(session, run, "JOB_STARTED", job_id=job.id, worker_id=worker_id, attempt=job.attempt)
                session.flush()
                data = record(job)
                data.pop("lease_hash", None)
                data["lease_token"] = token
                data["campaign_id"] = run.campaign_id
                data["remaining_wall_seconds"] = max(0, cfg.max_wall_seconds - (now() - run.created_at))
                data["remaining_gpu_seconds"] = max(0, cfg.max_gpu_seconds - run.stats["gpu_seconds"])
                return data
            return None

    def _check_lease(self, session, job, worker_id, token, allow_uncertain=False):
        supplied = hashlib.sha256((token or "").encode()).hexdigest()
        if job.worker_id != worker_id or not job.lease_hash or not hmac.compare_digest(job.lease_hash, supplied):
            raise DomainError("Lease does not belong to this worker", 403)
        run = required(session, Run, job.run_id)
        if run.state == RunState.CANCELLED:
            raise DomainError("Run was cancelled")
        permitted = {"LEASED", "SUCCEEDED"} | ({"UNCERTAIN"} if allow_uncertain else set())
        if job.status not in permitted:
            raise DomainError(f"Job is {job.status}; stale lease rejected")

    def heartbeat(self, job_id, worker_id, token, progress=None):
        with self.store.transaction() as session:
            job = required(session, Job, job_id, lock=True)
            self._check_lease(session, job, worker_id, token)
            run = required(session, Run, job.run_id, lock=True)
            cfg = RunConfig.model_validate(run.snapshot["config"])
            remaining = cfg.max_wall_seconds - (now() - run.created_at)
            if remaining <= 0:
                if job.kind == "SUMMARY":
                    job.status, job.completed_at = "CANCELLED", now()
                    emit(session, run, "SUMMARY_SKIPPED", reason="WALL_TIME_BUDGET_EXHAUSTED")
                    return {"cancelled": True, "reason": "Summary exceeded the run time budget"}
                self._review(session, run, "WALL_TIME_BUDGET_EXHAUSTED")
                job.status = "UNCERTAIN" if job.kind == "GENERATE" else "CANCELLED"
                return {"cancelled": True, "reason": run.stop_reason}
            job.lease_until = now() + self.settings.lease_seconds
            worker = required(session, Worker, worker_id)
            worker.heartbeat_at = now()
            if progress:
                job.progress = {**job.progress, "message": str(progress.get("message", ""))[:300],
                                "updated_at": now(), "phase": str(progress.get("phase", job.kind))[:50]}
                elapsed = progress.get("elapsed_seconds")
                if isinstance(elapsed, (int, float)) and 0 <= elapsed <= 86400:
                    job.progress = {**job.progress, "elapsed_seconds": elapsed}
            return {"cancelled": False, "lease_until": job.lease_until, "remaining_wall_seconds": remaining}

    def recover_expired(self):
        with self.store.transaction() as session:
            jobs = session.scalars(select(Job).where(Job.status == "LEASED", Job.lease_until < now()).with_for_update()).all()
            for job in jobs:
                run = required(session, Run, job.run_id, lock=True)
                if job.kind == "GENERATE":
                    job.status = "UNCERTAIN"
                    if run.state not in TERMINAL:
                        run.state, run.stop_reason = RunState.NEEDS_ATTENTION, "GENERATION_LEASE_LOST_RECONCILE_BEFORE_RETRY"
                elif job.attempt < job.max_attempts and run.state not in TERMINAL:
                    job.status, job.available_at = "RETRY", now() + min(60, 2 ** job.attempt)
                else:
                    job.status = "DEAD_LETTER"
                    if run.state not in TERMINAL and job.kind != "SUMMARY":
                        run.state, run.stop_reason = RunState.NEEDS_ATTENTION, "JOB_RETRIES_EXHAUSTED"
                job.error = {"code": "LEASE_EXPIRED", "detail": "Notebook heartbeat stopped; no result invented"}
                close_trace(session, job.progress.get("trace_id"), {"status": job.status}, "LeaseExpired")
                emit(session, run, "LEASE_EXPIRED", job_id=job.id, outcome=job.status)

    def complete(self, job_id, request: CompleteJob):
        result_hash = digest(request.result)
        with self.store.transaction() as session:
            job = required(session, Job, job_id, lock=True)
            self._check_lease(session, job, request.worker_id, request.lease_token, allow_uncertain=True)
            run = required(session, Run, job.run_id, lock=True)
            if job.status == "SUCCEEDED":
                if job.result_hash != result_hash:
                    raise DomainError("Completed result is immutable")
                return {"status": job.status, "run_id": run.id}
            was_uncertain = job.status == "UNCERTAIN"
            if job.kind == "PLAN":
                result = PlanResult.model_validate(request.result)
                self._validate_plan(session, run, job, result)
                self._enqueue(session, run, "REVIEW_PLAN", "typesafe", {**job.payload, "plan": result.model_dump()}, f"{job.id}:review")
            elif job.kind == "REVIEW_PLAN":
                result = PlanReview.model_validate(request.result)
                if result.plan_hash != digest(job.payload["plan"]):
                    raise DomainError("TypeSafe reviewed a different plan", 422)
                from .sponsors import TypeSafeKernel, ProviderFailure
                try:
                    choice, confidence, _ = TypeSafeKernel.validate_choice(result.raw_response.get("answers", {}).get("plan_gate"), {"APPROVE", "REJECT"})
                except (ProviderFailure, AttributeError) as exc:
                    raise DomainError("TypeSafe review receipt is invalid", 422) from exc
                if choice != result.choice or confidence != result.confidence or result.raw_response.get("model") != result.model:
                    raise DomainError("TypeSafe review receipt is inconsistent", 422)
                if result.choice != "APPROVE":
                    self._review(session, run, "TYPESAFE_PLAN_REJECTED")
                elif result.confidence < RunConfig.model_validate(run.snapshot["config"]).decision_confidence_floor:
                    self._review(session, run, "TYPESAFE_PLAN_LOW_CONFIDENCE")
                else:
                    self._complete_plan(session, run, job, PlanResult.model_validate(job.payload["plan"]))
            elif job.kind == "GENERATE":
                result = GenerationResult.model_validate(request.result)
                creative = required(session, Creative, job.creative_id)
                asset = required(session, Asset, result.asset_id)
                if asset.campaign_id != run.campaign_id or asset.job_id != job.id:
                    raise DomainError("Generated output must be uploaded by this job", 403)
                if asset.kind != run.snapshot["campaign"]["media_kind"]:
                    raise DomainError("Generator returned the wrong media type", 422)
                creative.output_asset_id, creative.generation, creative.status = asset.id, result.model_dump(), "GENERATED"
                self._account_result(run, result.model_dump())
            elif job.kind == "EVALUATE":
                result = EvaluationResult.model_validate(request.result)
                if result.evaluator != job.payload["evaluator"]:
                    raise DomainError("Evaluator identity does not match the assigned job", 422)
                for identity in result.artifact_ids:
                    artifact = required(session, Asset, identity)
                    if artifact.job_id != job.id or artifact.campaign_id != run.campaign_id:
                        raise DomainError("Evaluator artifact belongs to another job", 403)
                if result.evaluator == "tribe" and result.status == "SUCCEEDED" and not result.artifact_ids:
                    raise DomainError("TRIBE success requires its actual cortical artifact", 422)
                session.add(Evaluation(id=uid(), run_id=run.id, creative_id=job.creative_id, job_id=job.id,
                                       evaluator=result.evaluator, comparison_key=result.provenance.comparison_key, result=result.model_dump()))
                self._account_result(run, result.model_dump())
            elif job.kind == "DECIDE":
                result = DecisionResult.model_validate(request.result)
                self._complete_decision(session, run, job, result)
            elif job.kind == "SUMMARY":
                result = ExecutionSummary.model_validate(request.result)
                if result.input_digest != digest({"evidence": job.payload["evidence"], "execution": job.payload["execution"]}):
                    raise DomainError("Summary does not match its recorded input", 422)
                if not set(result.evidence_ids) <= {e["id"] for e in job.payload["evidence"]}:
                    raise DomainError("Summary cites unknown evidence", 422)
                model = session.get(Worker, job.worker_id).capabilities["summary"].get("model")
                if not model or result.provider_receipt.get("model") != model:
                    raise DomainError("Summary provider model does not match worker", 422)
                provenance = ModelProvenance(model=model, version="evidence-summary-v1", configuration_hash=digest({"contract": "evidence-summary-v1"}))
                for identity in job.payload["asset_ids"]:
                    session.add(NotebookEvidence(campaign_id=run.campaign_id, input_asset_id=identity,
                        source_receipt=f"summary-{job.id}-{identity}", source_kind="campaign_loop",
                        title="GLM — automatic run summary", evaluator="summary", comparison_key=provenance.comparison_key,
                        result={"evaluator": "summary", "status": "SUCCEEDED", "provenance": provenance.model_dump(),
                                "observations": result.model_dump(), "scores": {}, "artifact_ids": [],
                                "limitations": ["Explanation of recorded evidence; does not add measurements or override policy decisions."]}))
            else:
                raise DomainError("Unsupported job type", 422)
            job.result, job.result_hash, job.status = request.result, result_hash, "SUCCEEDED"
            # Previous failed attempts remain in JOB_FAILED events and traces.
            # The current successful job must not retain a live error badge.
            job.error = None
            job.completed_at = now()
            close_trace(session, job.progress.get("trace_id"), {"status": "SUCCEEDED", "creative_id": job.creative_id,
                         "model": request.result.get("model") or request.result.get("provenance", {}).get("model"),
                         "gpu_seconds": request.result.get("gpu_seconds"), "cost_usd": request.result.get("cost_usd"),
                         "decision": request.result.get("decision"), "confidence": request.result.get("confidence"),
                         "scores": request.result.get("scores"), "usage": request.result.get("usage"),
                         "plan_hash": request.result.get("plan_hash"), "plan_review": request.result.get("choice"),
                         "candidate_edits": [{"parent_creative_id": p.get("parent_creative_id"), "edit_intent_hash": digest(p.get("edit_intent"))} for p in request.result.get("candidates", [])],
                         "selected_creative_ids": request.result.get("selected_creative_ids"),
                         "response_delta": run.stats.get("last_gain") if job.kind == "DECIDE" else None,
                         "vision_receipt": request.result.get("observations", {}).get("provider_receipt")})
            emit(session, run, "JOB_COMPLETED", job_id=job.id, job_type=job.kind, creative_id=job.creative_id)
            if was_uncertain and run.stop_reason == "GENERATION_LEASE_LOST_RECONCILE_BEFORE_RETRY":
                run.state, run.stop_reason = RunState.GENERATING, None
            session.flush()
            self._advance(session, run, job.worker_id)
            if job.kind != "SUMMARY":
                self._queue_summary(session, run)
            return {"status": job.status, "run_id": run.id, "run_state": run.state}

    def _queue_summary(self, session, run):
        if run.state not in {RunState.READY_FOR_REVIEW, RunState.COMPLETE}:
            return
        last_work = session.scalar(select(Job).where(Job.run_id == run.id, Job.kind != "SUMMARY").order_by(Job.created_at.desc()))
        summary_key = f"{run.id}:summary:{last_work.id if last_work else 'empty'}"
        if session.scalar(select(Job.id).where(Job.idempotency_key == summary_key)):
            return
        online = session.scalars(select(Worker).where(Worker.heartbeat_at > now() - self.settings.worker_stale_seconds))
        if not any(w.capabilities.get("summary", {}).get("status") == "READY" for w in online):
            return
        creatives = list(session.scalars(select(Creative).where(Creative.run_id == run.id)))
        evidence = [record(e) for e in session.scalars(select(Evaluation).where(Evaluation.run_id == run.id))]
        execution = {"run": record(run), "creatives": [record(c) for c in creatives],
            "planning_receipts": [{"id": j.id, "kind": j.kind, "status": j.status, "result": j.result, "error": j.error} for j in session.scalars(select(Job).where(Job.run_id == run.id, Job.kind.in_(["PLAN", "REVIEW_PLAN"])))],
            "decisions": [record(d) for d in session.scalars(select(Decision).where(Decision.run_id == run.id))],
            "generation_receipts": [{"id": j.id, "status": j.status, "result": j.result} for j in session.scalars(select(Job).where(Job.run_id == run.id, Job.kind == "GENERATE"))]}
        self._enqueue(session, run, "SUMMARY", "summary", {"evidence": evidence, "execution": execution,
            "asset_ids": [c.output_asset_id for c in creatives if c.output_asset_id]}, summary_key)

    def retry_summary(self, run_id):
        """Retry explanation delivery without reopening a creative decision."""
        with self.store.transaction() as session:
            run = required(session, Run, run_id, lock=True)
            if run.state not in {RunState.READY_FOR_REVIEW, RunState.COMPLETE}:
                raise DomainError("The creative run must finish before retrying its summary")
            job = session.scalar(select(Job).where(Job.run_id == run.id, Job.kind == "SUMMARY").order_by(Job.created_at.desc()))
            if job is None:
                self._queue_summary(session, run)
            elif job.status == "FAILED" and job.attempt < job.max_attempts:
                job.status, job.available_at, job.lease_hash = "RETRY", now(), None
                emit(session, run, "SUMMARY_RETRY_REQUESTED", job_id=job.id)
            elif job.status not in {"SUCCEEDED", "PENDING", "RETRY", "LEASED"}:
                raise DomainError("Summary retry limit or budget reached")
            return {"run_id": run.id, "run_state": run.state}

    def _account_result(self, run, result):
        stats = dict(run.stats)
        stats["gpu_seconds"] += result.get("gpu_seconds", 0)
        if result.get("cost_usd") is None:
            stats["unknown_cost_jobs"] += 1
        else:
            stats["known_cost_usd"] += result["cost_usd"]
        run.stats = stats

    def _validate_plan(self, session, run, job, result):
        for plan in result.candidates:
            if not plan.parent_creative_id:
                continue
            hypothesis = plan.edit_intent.optimization
            if hypothesis is None:
                raise DomainError("Regeneration requires observation, visual evidence, hypothesis and modification", 422)
            evaluations = {e.id: e for e in session.scalars(select(Evaluation).where(Evaluation.creative_id == plan.parent_creative_id, Evaluation.run_id == run.id))}
            if not set(plan.edit_intent.reasoning_evidence_ids) <= set(evaluations):
                raise DomainError("Reasoning evidence IDs must identify parent evaluations, not creative or asset IDs", 422)
            observation = hypothesis.observation
            sensor = evaluations.get(observation.evaluation_id)
            visual = evaluations.get(hypothesis.creative_evidence.evaluation_id)
            if sensor is None or visual is None or visual.evaluator != "vision":
                raise DomainError("Optimization must cite parent response and vision evaluations", 422)
            score = sensor.result.get("scores", {}).get(observation.response_metric)
            if sensor.result.get("status") != "SUCCEEDED" or not score or score["value"] != observation.value:
                raise DomainError("Optimization observation does not match recorded score", 422)
            if observation.time_range is not None:
                raise DomainError("Aggregate scores cannot establish time-local response measurements", 422)
            if not {observation.evaluation_id, hypothesis.creative_evidence.evaluation_id} <= set(plan.edit_intent.reasoning_evidence_ids):
                raise DomainError("Optimization citations must be included in EditIntent evidence IDs", 422)

    def _complete_plan(self, session, run, job, result):
        self._validate_plan(session, run, job, result)
        slots = job.payload["candidate_slots"]
        if len(result.candidates) != len(slots):
            raise DomainError("Reasoner must fill exactly the allocated candidate slots", 422)
        cfg = RunConfig.model_validate(run.snapshot["config"])
        if len(result.candidates) + run.stats["generation_count"] > cfg.max_candidates:
            raise DomainError("Candidate budget exceeded", 422)
        for index, (plan, slot) in enumerate(zip(result.candidates, slots)):
            if plan.parent_creative_id != slot["parent_creative_id"]:
                raise DomainError("Reasoner cannot change creative lineage", 422)
            refs = list(run.snapshot["reference_asset_ids"])
            evidence_ids = set()
            if plan.parent_creative_id:
                parent = required(session, Creative, plan.parent_creative_id)
                if parent.run_id != run.id or not parent.output_asset_id:
                    raise DomainError("Regeneration parent must be a generated creative from this run", 422)
                refs = list(dict.fromkeys([parent.output_asset_id] + refs))
                evidence_ids = {e.id for e in session.scalars(select(Evaluation).where(Evaluation.creative_id == parent.id))}
                if not plan.edit_intent.reasoning_evidence_ids or not set(plan.edit_intent.reasoning_evidence_ids) <= evidence_ids:
                    raise DomainError("Regeneration requires valid parent evaluation evidence IDs", 422)
                locked = set(run.snapshot["campaign"]["brand"]["locked_requirements"])
                if not locked <= set(plan.edit_intent.preserve):
                    raise DomainError("EditIntent must preserve every locked brand requirement", 422)
            creative = Creative(id=uid(), run_id=run.id, campaign_id=run.campaign_id, parent_id=plan.parent_creative_id,
                                round=run.round, branch=index, creation_type=("text_alternative" if job.payload.get("conditioning") == "text_alternative" else "regeneration") if plan.parent_creative_id else "initial",
                                plan=plan.model_dump(), input_asset_ids=refs, status="QUEUED")
            session.add(creative)
            session.flush()
            payload = {"campaign": run.snapshot["campaign"], "creative_id": creative.id, "plan": plan.model_dump(), "conditioning": job.payload.get("conditioning", "media"),
                       "references": self._asset_refs(session, refs), "current_creative_asset_id": refs[0] if plan.parent_creative_id else None,
                       "media_kind": run.snapshot["campaign"]["media_kind"]}
            self._enqueue(session, run, "GENERATE", f"generate_{payload['media_kind']}", payload, f"{creative.id}:generate", creative.id)
        run.stats = {**run.stats, "generation_count": run.stats["generation_count"] + len(result.candidates)}
        run.state = RunState.GENERATING
        emit(session, run, "CREATIVE_STRATEGY", summary=result.summary, model=result.model, round=run.round)

    def fail(self, job_id, request: FailJob):
        with self.store.transaction() as session:
            job = required(session, Job, job_id, lock=True)
            self._check_lease(session, job, request.worker_id, request.lease_token, allow_uncertain=True)
            if job.status == "SUCCEEDED":
                raise DomainError("Cannot replace a completed result with a failure")
            run = required(session, Run, job.run_id, lock=True)
            self._account_result(run, request.model_dump())
            job.error = {"code": request.code, "detail": request.detail}
            if job.kind == "SUMMARY":
                job.status = "RETRY" if request.safe_to_retry and request.code in {"TRANSIENT", "INVALID_OUTPUT"} and job.attempt < job.max_attempts else "FAILED"
                job.available_at = now() + min(60, 2 ** job.attempt)
            elif request.code == "UNCERTAIN":
                job.status, run.state, run.stop_reason = "UNCERTAIN", RunState.NEEDS_ATTENTION, "UNKNOWN_PROVIDER_OUTCOME"
            elif request.safe_to_retry and (request.code in {"TRANSIENT", "OUT_OF_MEMORY"} or (request.code == "INVALID_OUTPUT" and job.kind in {"PLAN", "REVIEW_PLAN", "DECIDE"})) and job.attempt < job.max_attempts:
                job.status, job.available_at = "RETRY", now() + min(60, 2 ** job.attempt)
            else:
                job.status = "BLOCKED" if request.code in {"NOT_CONFIGURED", "UNAVAILABLE"} else "FAILED"
                if job.kind in {"PLAN", "REVIEW_PLAN", "DECIDE"} or job.status == "BLOCKED":
                    run.state, run.stop_reason = RunState.NEEDS_ATTENTION, request.code
                elif job.creative_id and job.kind == "GENERATE":
                    creative = required(session, Creative, job.creative_id)
                    creative.status, creative.rejection_reason = "FAILED", request.detail
            job.completed_at = now()
            close_trace(session, job.progress.get("trace_id"), {"status": job.status, "error_code": request.code}, request.code)
            emit(session, run, "JOB_FAILED", job_id=job.id, code=request.code, detail=request.detail, outcome=job.status)
            session.flush()
            self._advance(session, run, job.worker_id)
            return {"status": job.status, "run_state": run.state}

    def _media_constraints(self, session, run, creative):
        asset = required(session, Asset, creative.output_asset_id)
        spec = run.snapshot["campaign"]
        d = asset.details
        ratio = [int(x) for x in spec["aspect_ratio"].split(":")]
        actual = d.get("width", 0) / max(1, d.get("height", 0))
        ratio_ok = abs(actual - ratio[0] / ratio[1]) < 0.03
        duration_ok = spec["media_kind"] != "video" or abs(d.get("duration_seconds", 0) - spec["duration_seconds"]) <= 1.0
        return [{"name": "media_spec", "status": "PASS" if ratio_ok and duration_ok else "FAIL",
                 "evidence": f"Decoded media: {d}. Requested aspect {spec['aspect_ratio']}, duration {spec['duration_seconds']}."}]

    def _evidence(self, session, creative):
        run = required(session, Run, creative.run_id)
        evaluations = list(session.scalars(select(Evaluation).where(Evaluation.creative_id == creative.id).order_by(Evaluation.created_at)))
        latest = {e.evaluator: e for e in evaluations}
        required_names = set(run.snapshot["campaign"]["brand"]["locked_requirements"]) | {"approved_claims_only", "no_prohibited_claims"}
        hard = self._media_constraints(session, run, creative) if creative.output_asset_id else []
        vision = latest.get("vision")
        checks = {c["name"]: c for c in vision.result.get("constraints", [])} if vision else {}
        hard += [checks.get(name, {"name": name, "status": "UNKNOWN", "evidence": "No verified evaluator result for this requirement"}) for name in sorted(required_names)]
        delivery = vision.result.get("observations", {}).get("media_delivery") if vision else None
        if delivery in {"PROVIDER_REFUSAL", "UNUSABLE"}:
            hard.append({"name": "generated_media_delivered", "status": "FAIL",
                         "evidence": "Vision classified the actual pixels as " + delivery + "; this is not an ad deliverable."})
        scores = vision.result.get("scores", {}) if vision and vision.result["status"] == "SUCCEEDED" else {}
        quality = scores.get("creative_quality")
        cfg = RunConfig.model_validate(run.snapshot["config"])
        missing = [name for name in cfg.required_evaluators if name not in latest or latest[name].result["status"] != "SUCCEEDED"]
        eligible = bool(quality) and all(c["status"] == "PASS" for c in hard) and not missing
        # Only compare disagreement on an explicitly common, calibrated construct.
        alignment = defaultdict(list)
        for e in latest.values():
            contract = e.result.get("observations", {}).get("alignment_contract")
            value = e.result.get("scores", {}).get("target_alignment")
            if contract and isinstance(contract, str) and value:
                alignment[contract].append(value["value"])
        disagreement = max((max(v)-min(v) for v in alignment.values() if len(v) > 1), default=None)
        return {"creative_id": creative.id, "hard_constraints": hard, "evaluations": [record(e) for e in latest.values()],
                "quality": quality, "quality_comparison_key": vision.comparison_key if vision else None,
                "missing_required_evaluators": missing, "eligible": eligible, "evaluator_disagreement": disagreement,
                "interpretation": "Predicted proxies, not measured emotions, causal effects or purchasing outcomes."}

    def _evaluation_job(self, session, run, creative, evaluator, suffix=""):
        self._enqueue(session, run, "EVALUATE", f"evaluate_{evaluator}",
                      {"evaluator": evaluator, "campaign": run.snapshot["campaign"], "creative_id": creative.id,
                       "asset": self._asset_refs(session, [creative.output_asset_id])[0],
                       "references": self._asset_refs(session, run.snapshot["reference_asset_ids"]),
                       "required_constraints": run.snapshot["campaign"]["brand"]["locked_requirements"] + ["approved_claims_only", "no_prohibited_claims"]},
                      f"{creative.id}:evaluate:{evaluator}{suffix}", creative.id)

    def _advance(self, session, run, worker_id):
        if run.state in TERMINAL or run.state in PAUSED:
            return
        active = session.scalar(select(Job.id).where(Job.run_id == run.id, Job.status.in_(["PENDING", "RETRY", "LEASED", "UNCERTAIN", "BLOCKED"])).limit(1))
        if active:
            return
        failed_evaluation = session.scalar(select(Job.id).where(Job.run_id == run.id, Job.kind == "EVALUATE", Job.status.in_(["FAILED", "DEAD_LETTER"])).limit(1))
        if failed_evaluation:
            run.state, run.stop_reason = RunState.NEEDS_ATTENTION, "EVALUATION_FAILED"
            emit(session, run, "EVALUATION_REVIEW_REQUIRED", job_id=failed_evaluation)
            return
        creatives = list(session.scalars(select(Creative).where(Creative.run_id == run.id, Creative.round == run.round).order_by(Creative.branch)))
        generated = [c for c in creatives if c.output_asset_id and c.status != "INVALID"]
        if not generated:
            self._review(session, run, "NO_VALID_GENERATION")
            return
        all_evals = list(session.scalars(select(Evaluation).where(Evaluation.run_id == run.id)))
        done = {(e.creative_id, e.evaluator) for e in all_evals}
        cfg = RunConfig.model_validate(run.snapshot["config"])
        for creative in generated:
            if (creative.id, "vision") not in done:
                self._evaluation_job(session, run, creative, "vision")
                creative.status = "EVALUATING"
        session.flush()
        if any((c.id, "vision") not in done for c in generated):
            run.state = RunState.EVALUATING
            return
        # Screen on comparable vision quality, never a mixture of raw cortical and affect scales.
        evidence = {c.id: self._evidence(session, c) for c in generated}
        refused = {c.id for c in generated if any(e["evaluator"] == "vision" and e["result"].get("observations", {}).get("media_delivery") == "PROVIDER_REFUSAL" for e in evidence[c.id]["evaluations"])}
        valid = [c for c in generated if c.id not in refused and evidence[c.id]["quality"] and all(x["status"] == "PASS" for x in evidence[c.id]["hard_constraints"])]
        for c in generated:
            if c not in valid:
                c.status, c.rejection_reason = "INVALID", "Failed or unknown hard constraints, or missing creative-quality evidence"
                if c.id in refused:
                    c.rejection_reason = "Provider refusal placeholder detected by vision; no advertisement delivered"
        if not valid:
            if self._repair_constraints(session, run, generated, evidence):
                return
            self._review(session, run, "PROVIDER_REFUSAL_NO_AD_DELIVERED" if len(refused) == len(generated) else "INSUFFICIENT_EVIDENCE_OR_CONSTRAINT_FAILURE")
            return
        keys = {evidence[c.id]["quality_comparison_key"] for c in valid}
        if len(keys) != 1:
            self._review(session, run, "INCOMPATIBLE_VISION_EVALUATOR_CONFIGURATIONS")
            return
        promoted = sorted(valid, key=lambda c: evidence[c.id]["quality"]["value"], reverse=True)[:cfg.beam_width]
        for c in valid:
            if c not in promoted:
                c.status, c.rejection_reason = "SCREENED_OUT", "Not promoted by the bounded multi-fidelity screen; artifact preserved"
        worker = session.get(Worker, worker_id)
        online_workers = list(session.scalars(select(Worker).where(
            Worker.heartbeat_at > now() - self.settings.worker_stale_seconds)))
        queued = False
        for creative in promoted:
            for evaluator in list(dict.fromkeys(cfg.required_evaluators + cfg.optional_evaluators)):
                if evaluator == "vision" or (creative.id, evaluator) in done:
                    continue
                available = any(w.capabilities.get(f"evaluate_{evaluator}", {}).get("status") == "READY"
                                for w in online_workers)
                if available or evaluator in cfg.required_evaluators:
                    self._evaluation_job(session, run, creative, evaluator)
                    queued = True
                else:
                    emit(session, run, "OPTIONAL_EVALUATOR_UNAVAILABLE", creative_id=creative.id, evaluator=evaluator)
        if queued:
            run.state = RunState.EVALUATING
            return
        if run.champion_id and run.champion_id not in {c.id for c in promoted}:
            champion = required(session, Creative, run.champion_id)
            promoted.append(champion)
        bundles = [self._evidence(session, c) for c in promoted]
        if any(not b["eligible"] for b in bundles):
            self._review(session, run, "REQUIRED_EVALUATION_UNAVAILABLE")
            return
        for evaluator in cfg.required_evaluators:
            compatible = {next(e["comparison_key"] for e in b["evaluations"] if e["evaluator"] == evaluator) for b in bundles}
            if len(compatible) != 1:
                self._review(session, run, f"INCOMPATIBLE_{evaluator.upper()}_CONFIGURATIONS")
                return
        if any(b["evaluator_disagreement"] is not None and b["evaluator_disagreement"] > cfg.evaluator_disagreement_limit for b in bundles):
            self._review(session, run, "EVALUATOR_DISAGREEMENT_REQUIRES_REVIEW")
            return
        payload = {"campaign": run.snapshot["campaign"], "config": cfg.model_dump(), "round": run.round,
                   "stats": run.stats, "evidence_bundles": bundles, "allowed_creative_ids": [c.id for c in promoted],
                   "allowed_actions": ["KEEP", "REGENERATE", "GENERATE_ALTERNATIVE", "RUN_MORE_EVALUATION", "ASK_HUMAN", "READY_FOR_DEPLOYMENT", "STOP", "REJECT"],
                   "incumbent_creative_id": run.champion_id,
                   "history": [record(d) for d in session.scalars(select(Decision).where(Decision.run_id == run.id))]}
        capability = "generate_" + run.snapshot["campaign"]["media_kind"]
        generators = [w.capabilities[capability] for w in online_workers
                      if w.capabilities.get(capability, {}).get("status") == "READY"]
        generator = generators[0] if generators else {}
        if generator.get("supports_regeneration") is False:
            payload["allowed_actions"].remove("REGENERATE")
        if not any(b["quality"]["value"] >= cfg.quality_threshold for b in bundles):
            payload["allowed_actions"].remove("READY_FOR_DEPLOYMENT")
        payload["generator_contract"] = generator
        self._enqueue(session, run, "DECIDE", "typesafe", payload, f"{run.id}:decide:{run.round}:{run.stats.get('extra_evaluations',0)}")
        run.state = RunState.DECIDING

    def _repair_constraints(self, session, run, generated, evidence):
        """Propose a bounded correction; failed outputs never become eligible winners."""
        cfg = RunConfig.model_validate(run.snapshot["config"])
        if (self._budget_reason(run, cfg) or run.round + 1 >= cfg.max_rounds
                or run.stats["generation_count"] >= cfg.max_candidates):
            return False
        repairable = []
        for creative in generated:
            bundle = evidence[creative.id]
            vision = next((e["result"] for e in bundle["evaluations"] if e["evaluator"] == "vision"), {})
            checks = bundle["hard_constraints"]
            if (vision.get("status") == "SUCCEEDED"
                    and vision.get("observations", {}).get("media_delivery") == "GENERATED_MEDIA"
                    and bundle.get("quality") and any(c["status"] == "FAIL" for c in checks)
                    and all(c["status"] in {"PASS", "FAIL"} for c in checks)):
                repairable.append(creative)
        if not repairable:
            return False
        capability = "generate_" + run.snapshot["campaign"]["media_kind"]
        generators = [w.capabilities[capability] for w in session.scalars(select(Worker))
                      if w.heartbeat_at > now() - self.settings.worker_stale_seconds
                      and w.capabilities.get(capability, {}).get("status") == "READY"]
        if not generators:
            return False
        parents = repairable[:cfg.beam_width]
        for parent in parents:
            parent.status = "INVALID"
        run.round += 1
        run.stop_reason = None
        emit(session, run, "CONSTRAINT_REPAIR_REQUESTED", parent_ids=[p.id for p in parents],
             detail="Failed outputs remain ineligible. A corrective plan must pass TypeSafe before generation.")
        self._plan_job(session, run, parents,
                       conditioning="text_alternative" if generators[0].get("supports_regeneration") is False else "media",
                       constraint_repair=True)
        return True

    def retry_constraint_repair(self, run_id):
        with self.store.transaction() as session:
            run = required(session, Run, run_id, lock=True)
            if run.state != RunState.READY_FOR_REVIEW or run.stop_reason != "INSUFFICIENT_EVIDENCE_OR_CONSTRAINT_FAILURE":
                raise DomainError("Only a run stopped on failed output constraints can request this repair")
            if session.scalar(select(Job.id).where(Job.run_id == run.id, Job.status.in_(["LEASED", "PENDING", "RETRY"]))):
                raise DomainError("Wait for pending run jobs before requesting repair")
            generated = list(session.scalars(select(Creative).where(Creative.run_id == run.id, Creative.round == run.round, Creative.output_asset_id.is_not(None))))
            evidence = {c.id: self._evidence(session, c) for c in generated}
            if not self._repair_constraints(session, run, generated, evidence):
                raise DomainError("No repairable evidence, generator, or remaining budget")
            return record(run)

    def correct_invalid_plan(self, run_id):
        """Correct a demonstrably invalid stored plan, never reroll a valid gate decision."""
        with self.store.transaction() as session:
            run = required(session, Run, run_id, lock=True)
            if run.state != RunState.READY_FOR_REVIEW or not (run.stop_reason or "").startswith("TYPESAFE_PLAN"):
                raise DomainError("Only a stopped plan review can be checked for a contract correction")
            job = session.scalar(select(Job).where(Job.run_id == run.id, Job.kind == "PLAN", Job.status == "SUCCEEDED").order_by(Job.created_at.desc()))
            if not job or job.payload.get("validation_correction"):
                raise DomainError("No uncorrected plan is available")
            try:
                self._validate_plan(session, run, job, PlanResult.model_validate(job.result))
            except DomainError as error:
                correction = error.detail
            else:
                raise DomainError("This plan passes its contract; its review cannot be bypassed")
            if self._budget_reason(run, RunConfig.model_validate(run.snapshot["config"])):
                raise DomainError("Run budget exhausted")
            payload = {**job.payload, "validation_correction": correction}
            self._enqueue(session, run, "PLAN", "reasoner", payload, f"{job.id}:validation-correction")
            run.state, run.stop_reason = RunState.REGENERATING if run.round else RunState.PLANNING, None
            emit(session, run, "INVALID_PLAN_CORRECTION_REQUESTED", previous_job_id=job.id, validation_error=correction)
            return record(run)

    def _complete_decision(self, session, run, job, result):
        allowed = set(job.payload["allowed_creative_ids"])
        if result.decision not in job.payload["allowed_actions"] or not set(result.selected_creative_ids) <= allowed:
            raise DomainError("TypeSafe returned an unauthorized action or creative", 422)
        cfg = RunConfig.model_validate(run.snapshot["config"])
        if len(result.selected_creative_ids) > cfg.beam_width:
            raise DomainError("Selection exceeds beam width", 422)
        selected = result.selected_creative_ids
        action, override = result.decision, None
        if result.confidence < cfg.decision_confidence_floor:
            action, override = "ASK_HUMAN", "TypeSafe confidence is below the configured floor"
        if action not in {"REJECT", "STOP", "ASK_HUMAN"} and not selected:
            raise DomainError("Decision requires an explicit eligible candidate", 422)
        bundles = {b["creative_id"]: b for b in job.payload["evidence_bundles"]}
        if selected:
            old_quality = bundles.get(run.champion_id, {}).get("quality", {}).get("value")
            new_quality = bundles[selected[0]]["quality"]["value"]
            gain = None if old_quality is None else new_quality - old_quality
            if gain is not None and gain < 0 and action not in {"ASK_HUMAN", "STOP", "REJECT"}:
                # A lower-scoring proposal cannot silently replace the incumbent.
                # The comparison here is only the common vision-quality proxy.
                selected = [run.champion_id]
                new_quality = old_quality
                action, override = "KEEP", "REVERTED_LOWER_PROXY_QUALITY"
            run.stats = {**run.stats, "plateau": (run.stats["plateau"] + 1) if gain is not None and gain < cfg.min_improvement else 0,
                         "last_proxy_quality": new_quality, "last_gain": gain, "last_decision": result.model_dump(exclude={"raw_response"})}
            run.champion_id, run.selected_ids = selected[0], selected
        for identity in allowed:
            c = required(session, Creative, identity)
            if c.round == run.round:
                c.status = "SELECTED" if identity in selected else "REJECTED"
                c.rejection_reason = None if identity in selected else "Not selected by the evidence-backed decision"
            existing = session.scalar(select(Intervention).where(Intervention.creative_id == c.id))
            if not existing:
                parent_score = self._evidence(session, required(session, Creative, c.parent_id))["quality"] if c.parent_id else None
                score = bundles[identity]["quality"]
                session.add(Intervention(id=uid(), creative_id=c.id, campaign_id=run.campaign_id, run_id=run.id,
                            context_key=digest({"brand": run.snapshot["campaign"]["brand"], "objective": run.snapshot["campaign"]["objective"],
                                              "platform": run.snapshot["campaign"]["platform"], "evaluator": bundles[identity]["quality_comparison_key"]}),
                            strategy=c.plan["strategy"], observation={"selected": identity in selected, "quality": score,
                            "parent_quality": parent_score, "attribution_quality": "variant_level", "real_outcome": None,
                            "meaning": "Contextual selection observation; not a causal or commercial win"}))
        reason = self._budget_reason(run, cfg)
        if action in {"REGENERATE", "GENERATE_ALTERNATIVE"}:
            if run.round + 1 >= cfg.max_rounds:
                reason = "GENERATION_ROUND_LIMIT"
            elif run.stats["generation_count"] >= cfg.max_candidates:
                reason = "CANDIDATE_BUDGET_EXHAUSTED"
            elif run.stats["plateau"] >= cfg.plateau_rounds:
                reason = "SEARCH_PLATEAU"
            elif run.stats.get("last_proxy_quality", 0) >= cfg.quality_threshold:
                reason = "PROXY_QUALITY_THRESHOLD_REACHED"
            if reason:
                action, override = "ASK_HUMAN", reason
        session.add(Decision(id=uid(), run_id=run.id, round=run.round, job_id=job.id,
                             evidence=job.payload, result=result.model_dump(), applied_action=action, override_reason=override))
        emit(session, run, "DECISION", action=action, proposed_action=result.decision, confidence=result.confidence,
             selected_creative_ids=selected, override_reason=override, reason_codes=result.reason_codes)
        if action in {"REGENERATE", "GENERATE_ALTERNATIVE"}:
            run.round += 1
            parents = [required(session, Creative, identity) for identity in selected]
            # Text-only generators keep evidence lineage, but must not claim to
            # edit the parent's pixels. Media-capable alternatives still use them.
            conditioning = "text_alternative" if action == "GENERATE_ALTERNATIVE" and job.payload.get("generator_contract", {}).get("supports_regeneration") is False else "media"
            self._plan_job(session, run, parents, conditioning=conditioning)
        elif action == "RUN_MORE_EVALUATION":
            if run.stats.get("extra_evaluations", 0) >= 1:
                self._review(session, run, "EXTRA_EVALUATION_LIMIT")
            else:
                run.stats = {**run.stats, "extra_evaluations": 1}
                for identity in selected:
                    self._evaluation_job(session, run, required(session, Creative, identity), "vision", ":review")
                run.state = RunState.EVALUATING
        else:
            # READY_FOR_DEPLOYMENT is a recommendation, NEVER human approval.
            self._review(session, run, override or action)

    def _review(self, session, run, reason):
        run.state, run.stop_reason = RunState.READY_FOR_REVIEW, reason
        emit(session, run, "REVIEW_REQUIRED", reason=reason, selected_creative_ids=run.selected_ids)

    def _cancel_pending(self, session, run):
        for job in session.scalars(select(Job).where(Job.run_id == run.id, Job.status.in_(["PENDING", "RETRY", "BLOCKED"]))):
            job.status, job.completed_at = "CANCELLED", now()

    def cancel(self, run_id):
        with self.store.transaction() as session:
            run = required(session, Run, run_id, lock=True)
            if run.state in TERMINAL:
                return record(run)
            run.state, run.stop_reason = RunState.CANCELLED, "USER_CANCELLED"
            for job in session.scalars(select(Job).where(Job.run_id == run.id, Job.status.in_(["PENDING", "RETRY", "BLOCKED", "LEASED", "UNCERTAIN"]))):
                job.status, job.completed_at = "CANCELLED", now()
                close_trace(session, job.progress.get("trace_id"), {"status": "CANCELLED"}, "UserCancelled")
            close_trace(session, run.id, {"status": "CANCELLED"})
            emit(session, run, "CANCELLED", reason="Human requested cancellation; in-flight notebook receives cancellation on heartbeat")
            return record(run)

    def resume(self, run_id, acknowledge_uncertain_cost=False):
        with self.store.transaction() as session:
            run = required(session, Run, run_id, lock=True)
            if run.state != RunState.NEEDS_ATTENTION:
                raise DomainError("Only a blocked run can resume; completed/reviewed runs remain immutable")
            jobs = list(session.scalars(select(Job).where(Job.run_id == run.id, Job.status.in_(["BLOCKED", "UNCERTAIN", "DEAD_LETTER", "FAILED"])) ))
            if any(j.status == "UNCERTAIN" for j in jobs) and not acknowledge_uncertain_cost:
                raise DomainError("Reconcile the notebook journal first. Explicit acknowledgement is required before retrying an uncertain paid generation")
            for job in jobs:
                if job.attempt >= job.max_attempts:
                    raise DomainError("Retry limit reached; create a new budgeted run rather than bypassing it")
                job.status, job.available_at, job.lease_hash = "RETRY", now(), None
            next_kind = min(jobs, key=lambda j: j.created_at).kind if jobs else "GENERATE"
            run.state = {"PLAN": RunState.PLANNING if run.round == 0 else RunState.REGENERATING,
                         "REVIEW_PLAN": RunState.PLANNING, "EVALUATE": RunState.EVALUATING,
                         "DECIDE": RunState.DECIDING}.get(next_kind, RunState.GENERATING)
            run.stop_reason = None
            emit(session, run, "RESUMED", uncertainty_acknowledged=acknowledge_uncertain_cost)
            return record(run)

    def feedback(self, campaign_id, request: FeedbackRequest, actor="human"):
        with self.store.transaction() as session:
            creative = required(session, Creative, request.creative_id)
            if creative.campaign_id != campaign_id:
                raise DomainError("Feedback belongs to another campaign", 403)
            feedback = Feedback(id=uid(), campaign_id=campaign_id, actor=actor, **request.model_dump())
            session.add(feedback)
            run = required(session, Run, creative.run_id, lock=True)
            emit(session, run, "HUMAN_FEEDBACK", creative_id=creative.id, feedback_kind=request.kind, text=request.text)
            session.flush()
            return record(feedback)

    def snapshot(self, run_id):
        self.recover_expired()
        with self.store.read() as session:
            run = required(session, Run, run_id)
            creatives = list(session.scalars(select(Creative).where(Creative.run_id == run_id).order_by(Creative.created_at)))
            return {"experiments": [record(e) for e in session.scalars(select(Deployment).where(Deployment.run_id == run_id))], "run": record(run), "creatives": [{**record(c), "evidence": self._evidence(session, c) if c.output_asset_id else None} for c in creatives],
                    "jobs": [{k: v for k, v in record(j).items() if k != "lease_hash"} for j in session.scalars(select(Job).where(Job.run_id == run_id).order_by(Job.created_at))],
                    "events": [record(e) for e in session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.id).limit(2000))],
                    "decisions": [record(d) for d in session.scalars(select(Decision).where(Decision.run_id == run_id).order_by(Decision.created_at))],
                    "traces": [record(t) for t in session.scalars(select(Trace).where(Trace.run_id == run_id).order_by(Trace.started_at))]}

    def campaign_detail(self, campaign_id):
        with self.store.read() as session:
            campaign = required(session, Campaign, campaign_id)
            return {"campaign": record(campaign), "assets": [record(a) for a in session.scalars(select(Asset).where(Asset.campaign_id == campaign_id).order_by(Asset.created_at))],
                    "runs": [record(r) for r in session.scalars(select(Run).where(Run.campaign_id == campaign_id).order_by(Run.created_at.desc()))],
                    "feedback": [record(f) for f in session.scalars(select(Feedback).where(Feedback.campaign_id == campaign_id).order_by(Feedback.created_at.desc()))]}

    def propose_policy(self, proposal: ResearchProposal):
        with self.store.transaction() as session:
            for identity in proposal.evidence_run_ids:
                required(session, Run, identity)
            row = PolicyProposal(id=uid(), proposal=proposal.model_dump(), digest=digest(proposal.model_dump()), status="PROPOSED")
            session.add(row)
            session.flush()
            return record(row)

    def learning(self):
        with self.store.read() as session:
            return {"observations": [record(i) for i in session.scalars(select(Intervention).order_by(Intervention.created_at.desc()).limit(500))],
                    "policy_proposals": [record(p) for p in session.scalars(select(PolicyProposal).order_by(PolicyProposal.created_at.desc()).limit(100))],
                    "interpretation": "Observational strategy memory. Generalization and commercial improvement are not established; policy activation requires held-out replay."}
