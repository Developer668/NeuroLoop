"""Execution readiness and decision gates derived from the authoritative V2 engine."""
from collections import Counter
from sqlalchemy import select
from .db import Evaluation


def readiness(session, store, runs, jobs, creatives, decisions, assets):
    # Use exactly the eligibility rules used to admit candidates to decisions.
    from .engine import LoopEngine
    engine = LoopEngine(store, None)
    candidates, ladder, gates = [], [], []
    evaluations = list(session.scalars(select(Evaluation)))
    generated = {}
    for creative in creatives:
        asset = assets.get(creative.output_asset_id)
        job = next((j for j in jobs if j.creative_id == creative.id and j.kind == 'GENERATE'
                    and j.status == 'SUCCEEDED' and (j.result or {}).get('asset_id') == creative.output_asset_id), None)
        # Review eligibility is distinct from whether a real generation ran.
        # Preserve generated media and completed evaluation evidence even when
        # a later constraint check rejects the candidate.
        if not asset or not job:
            continue
        generated[creative.id] = creative
        bundle = engine._evidence(session, creative)
        counts = Counter(c['status'] for c in bundle['hard_constraints'])
        candidates.append({'run_id': creative.run_id, 'creative_id': creative.id, 'parent_id': creative.parent_id,
            'generation_job_id': job.id, 'asset_id': asset.id, 'asset_sha256': asset.sha256,
            'eligible': bundle['eligible'], 'required_evidence_complete': not bundle['missing_required_evaluators'],
            'missing_evaluators': ', '.join(bundle['missing_required_evaluators']),
            'constraints_pass': counts['PASS'], 'constraints_fail': counts['FAIL'], 'constraints_unknown': counts['UNKNOWN']})
    eligible = {c['creative_id'] for c in candidates if c['eligible']}
    for run in runs:
        rjobs = [j for j in jobs if j.run_id == run.id]
        rdecisions = [d for d in decisions if d.run_id == run.id]
        floor = run.snapshot.get('config', {}).get('decision_confidence_floor', .7)
        reviews = [j for j in rjobs if j.kind == 'REVIEW_PLAN' and j.status == 'SUCCEEDED']
        for job in reviews:
            result = job.result or {}
            confidence = result.get('confidence')
            gates.append({'run_id': run.id, 'job_id': job.id, 'stage': 'plan_review',
                'proposed_action': result.get('choice'), 'applied_action': 'APPROVE' if result.get('choice') == 'APPROVE'
                and isinstance(confidence, (int, float)) and confidence >= floor else 'BLOCK',
                'confidence': confidence, 'confidence_floor': floor, 'engine_override': None})
        for decision in rdecisions:
            gates.append({'run_id': run.id, 'job_id': decision.job_id, 'stage': 'final_decision',
                'proposed_action': decision.result.get('decision'), 'applied_action': decision.applied_action,
                'confidence': decision.result.get('confidence'), 'confidence_floor': floor,
                'engine_override': bool(decision.override_reason)})
        rgenerated = [c for c in generated.values() if c.run_id == run.id]
        evaluated = {e.creative_id for e in evaluations if e.run_id == run.id and e.evaluator == 'vision'
                     and e.result.get('status') == 'SUCCEEDED' and e.creative_id in generated}
        # A completed child must descend from an eligible parent selected by an applied revision decision.
        children = [c for c in rgenerated if c.parent_id in eligible and any(
            d.applied_action in {'REGENERATE', 'GENERATE_ALTERNATIVE'}
            and c.parent_id in d.result.get('selected_creative_ids', []) and c.created_at >= d.created_at
            and c.round > d.round for d in rdecisions)]
        row = {'run_id': run.id, 'attempted': any(j.attempt > 0 for j in rjobs),
            'control_plane_verified': any(j.status == 'SUCCEEDED' for j in rjobs),
            'plan_review_verified': bool(reviews),
            'plan_approved': any(g['run_id'] == run.id and g['stage'] == 'plan_review' and g['applied_action'] == 'APPROVE' for g in gates),
            'generation_verified': bool(rgenerated), 'vision_verified': bool(evaluated),
            'eligible_evidence_verified': any(c.id in eligible for c in rgenerated),
            'decision_verified': bool(rdecisions), 'child_generation_verified': bool(children)}
        row['full_loop_verified'] = all(row[k] for k in ('control_plane_verified', 'plan_approved', 'generation_verified',
            'vision_verified', 'eligible_evidence_verified', 'decision_verified', 'child_generation_verified'))
        ladder.append(row)
    rate = lambda n, d: n / d if d else None
    attempted = sum(r['attempted'] for r in ladder)
    final = [g for g in gates if g['stage'] == 'final_decision']
    return {'readiness': ladder, 'candidate_evidence': candidates, 'decision_gates': gates,
        'readiness_stages': [{'stage': k, 'verified_runs': sum(r[k] for r in ladder), 'attempted_runs': attempted}
            for k in ('control_plane_verified', 'plan_review_verified', 'plan_approved', 'generation_verified',
                      'vision_verified', 'eligible_evidence_verified', 'decision_verified', 'child_generation_verified', 'full_loop_verified')],
        'metrics': {'verification_runs_attempted': attempted,
            'plan_to_generation_rate': rate(sum(r['plan_approved'] and r['generation_verified'] for r in ladder), sum(r['plan_approved'] for r in ladder)),
            'decision_to_child_generation_rate': rate(sum(r['decision_verified'] and r['child_generation_verified'] for r in ladder), sum(r['decision_verified'] for r in ladder)),
            'full_loop_verified_rate': rate(sum(r['full_loop_verified'] for r in ladder), attempted),
            'eligible_candidate_rate': rate(len(eligible), len(candidates)),
            'required_evidence_completion_rate': rate(sum(c['required_evidence_complete'] for c in candidates), len(candidates)),
            'engine_override_rate': rate(sum(g['engine_override'] for g in final), len(final)),
            'decision_human_escalation_rate': rate(sum(g['applied_action'] == 'ASK_HUMAN' for g in final), len(final))}}
