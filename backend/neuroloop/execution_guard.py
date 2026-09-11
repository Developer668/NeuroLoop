"""Persistent execution hold and conservative runtime pressure checks.

These controls reduce exposure; they do not diagnose or prevent driver failures.
Reviewing saved data never requires clearing the hold.
"""
import json
from .config import settings
from .persistence import atomic_json


def execution_status():
    path = settings().data / 'inference-quarantine.json'
    if not path.exists():
        return {'paused': False, 'reason': None}
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        reason = record.get('reason', 'Execution hold requires review')
    except (OSError, ValueError):
        reason = 'Execution hold could not be read; review is required'
    return {'paused': True, 'reason': reason}


def require_execution_enabled():
    if execution_status()['paused']:
        raise RuntimeError('Inference and Launch are paused after a graphics crash. Saved evidence remains available. Resolve the execution hold before starting model work.')


def pressure_reason(state):
    gpu = state.get('gpu')
    if not gpu:
        return 'GPU telemetry became unavailable during execution'
    if gpu['temperature_c'] >= 82:
        return 'GPU reached the conservative 82°C execution limit'
    if state['ram_available_bytes'] < 3 * 1024**3:
        return 'Available system memory fell below the 3 GiB execution reserve'
    return None


def hold_execution(reason, run_id, telemetry):
    from .db import now
    atomic_json(settings().data / 'inference-quarantine.json', {
        'version': 1, 'active': True, 'reason': reason, 'created_at': now(),
        'interrupted_run_id': run_id, 'telemetry': telemetry,
        'cause_confirmed': False,
        'resume_requirement': 'Review diagnostics and explicitly approve a revised bounded test; no automatic retry.'})
