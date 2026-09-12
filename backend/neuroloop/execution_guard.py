"""Persistent execution hold and conservative runtime pressure checks.

These controls reduce exposure; they do not diagnose or prevent driver failures.
Reviewing saved data never requires clearing the hold.
"""
import json
import os
import sys
from .config import settings
from .persistence import atomic_json


def _cpu_verification_environment() -> bool:
    return (os.getenv('NEUROLOOP_CPU_VERIFICATION', '').strip().lower() == 'true'
            and os.getenv('NEUROLOOP_INFERENCE_DEVICE', '').strip().lower() == 'cpu'
            and 'CUDA_VISIBLE_DEVICES' in os.environ
            and os.environ['CUDA_VISIBLE_DEVICES'].strip() in {'', '-1'})


# Latch before torch can initialize CUDA. Later environment changes cannot
# establish an exemption in a running API/Launch process.
_CPU_VERIFICATION_BOOTSTRAPPED = _cpu_verification_environment() and 'torch' not in sys.modules


def cpu_verification_enabled() -> bool:
    """Explicit standalone CPU verification; never clears the GPU hold."""
    return _CPU_VERIFICATION_BOOTSTRAPPED and _cpu_verification_environment()


def mac_mps_override_enabled() -> bool:
    """Allow only an explicit Apple Silicon test to bypass the Windows hold."""
    return sys.platform == 'darwin' and os.getenv('NEUROLOOP_ALLOW_MPS_INFERENCE', '').lower() in {'1', 'true', 'yes'}


def memory_reserve_bytes() -> int:
    """Return the minimum free RAM allowed for the current bounded run."""
    reserve_gib = 4.0 if cpu_verification_enabled() else 3.0
    if mac_mps_override_enabled():
        try:
            # 1.5 GiB is a hard safety floor for Apple unified memory. A
            # caller may request a more conservative reserve, never a lower one.
            reserve_gib = min(3.0, max(1.5, float(os.getenv('NEUROLOOP_MPS_MEMORY_RESERVE_GIB', '1.5'))))
        except ValueError:
            reserve_gib = 3.0
    return int(reserve_gib * 1024**3)


def execution_status():
    path = settings().data / 'inference-quarantine.json'
    if not path.exists():
        if cpu_verification_enabled():
            return {'paused': False, 'reason': None, 'execution_scope': 'cpu_only_verification', 'gpu_allowed': False}
        return {'paused': False, 'reason': None}
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        reason = record.get('reason', 'Execution hold requires review')
    except (OSError, ValueError):
        reason = 'Execution hold could not be read; review is required'
    if cpu_verification_enabled():
        return {'paused': False, 'reason': reason, 'hold_override': 'explicit CPU-only verification; GPU hold preserved',
                'execution_scope': 'cpu_only_verification', 'gpu_allowed': False, 'gpu_hold_preserved': True}
    if mac_mps_override_enabled():
        return {'paused': False, 'reason': reason, 'hold_override': 'explicit Apple Silicon MPS test; Windows hold preserved'}
    return {'paused': True, 'reason': reason}


def require_execution_enabled():
    if execution_status()['paused']:
        raise RuntimeError('Inference and Launch are paused after a graphics crash. Saved evidence remains available. Resolve the execution hold before starting model work.')


def pressure_reason(state):
    if state.get('accelerator') in {'mps', 'cpu'}:
        reserve=memory_reserve_bytes()
        if state['ram_available_bytes'] < reserve:
            return f'Available system memory fell below the {reserve / 1024**3:.1f} GiB execution reserve'
        return None
    gpu = state.get('gpu')
    if not gpu:
        return 'GPU telemetry became unavailable during execution'
    if gpu['temperature_c'] >= 82:
        return 'GPU reached the conservative 82°C execution limit'
    reserve=memory_reserve_bytes()
    if state['ram_available_bytes'] < reserve:
        return f'Available system memory fell below the {reserve / 1024**3:.1f} GiB execution reserve'
    return None


def hold_execution(reason, run_id, telemetry):
    from .db import now
    if cpu_verification_enabled():
        # CPU pressure must stop the owned diagnostic child without replacing
        # the original GPU crash record or granting future execution.
        atomic_json(settings().data / 'cpu-verification-abort.json', {
            'reason': reason, 'run_id': run_id, 'telemetry': telemetry, 'created_at': now(),
            'execution_scope': 'cpu_only_verification', 'gpu_hold_preserved': True})
        return
    atomic_json(settings().data / 'inference-quarantine.json', {
        'version': 1, 'active': True, 'reason': reason, 'created_at': now(),
        'interrupted_run_id': run_id, 'telemetry': telemetry,
        'cause_confirmed': False,
        'resume_requirement': 'Review diagnostics and explicitly approve a revised bounded test; no automatic retry.'})
