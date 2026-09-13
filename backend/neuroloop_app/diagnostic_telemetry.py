"""Bounded, metadata-only operational tables for the web observability page."""
from sqlalchemy import select
from .db import Worker, Event, ArtifactBackup


def diagnostics(session, jobs, traces, evidence):
    allowed = {'job_id', 'job_type', 'creative_id', 'worker_id', 'attempt', 'round', 'action',
               'proposed_action', 'confidence', 'code', 'outcome', 'evaluator', 'asset_id'}
    events = list(session.scalars(select(Event).order_by(Event.created_at.desc()).limit(1000)))
    workers = list(session.scalars(select(Worker)))
    backups = list(session.scalars(select(ArtifactBackup)))
    capability_rows = []
    for worker in workers:
        for capability, registration in worker.capabilities.items():
            succeeded = [j for j in jobs if j.worker_id == worker.id and j.capability == capability and j.status == 'SUCCEEDED']
            last = max(succeeded, key=lambda j: j.completed_at or 0, default=None)
            registration = registration if isinstance(registration, dict) else {}
            provenance = registration.get('provenance') or {}
            capability_rows.append({'worker_id': worker.id, 'provider': worker.provider, 'capability': capability,
                'registered_status': registration.get('status', 'REGISTERED'),
                'execution_status': 'EXECUTION_VERIFIED' if last else 'NO_CAMPAIGN_EXECUTION',
                'successful_jobs': len(succeeded), 'last_success_at': last.completed_at if last else None,
                'heartbeat_at': worker.heartbeat_at, 'model': provenance.get('model')})
    return {
        'events': [{'event_id': e.id, 'created_at': e.created_at, 'run_id': e.run_id, 'event': e.kind,
                    **{k: v for k, v in e.detail.items() if k in allowed}} for e in events],
        'event_limit': 1000,
        'trace_log': [{'trace_id': t.id, 'parent_id': t.parent_id, 'run_id': t.run_id, 'stage': t.name,
                       'started_at': t.started_at, 'ended_at': t.ended_at, 'delivery': t.status,
                       'status': 'FAILED' if t.exception else ('COMPLETED' if t.ended_at else 'OPEN'),
                       'weave_url': t.url} for t in traces],
        'capabilities': capability_rows,
        'artifact_delivery': [{'backup_id': b.id, 'category': b.id.split('-', 1)[0], 'status': b.status,
                               'updated_at': b.updated_at, 'content_sha256': b.content_hash, 'artifact_url': b.url}
                              for b in backups],
        'model_receipts': [{'evidence_id': e.id, 'asset_id': e.input_asset_id, 'evaluator': e.evaluator,
                            'created_at': e.created_at, 'status': e.result.get('status'),
                            'model': (e.result.get('provenance') or {}).get('model'),
                            'comparison_key': e.comparison_key, 'source': e.source_kind} for e in evidence],
    }
