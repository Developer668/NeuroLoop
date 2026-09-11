"""Read-only laptop telemetry. Never changes driver, clocks, power, or registry settings."""
import shutil
import subprocess
import time
import psutil

_cached=None
_checked=0.0

def hardware_status():
    global _cached,_checked
    if _cached is not None and time.monotonic()-_checked<3:
        return _cached
    ram=psutil.virtual_memory()
    result={'ram_total_bytes':ram.total,'ram_available_bytes':ram.available,'gpu':None,'accelerator':None}
    executable=shutil.which('nvidia-smi')
    if executable:
        try:
            completed=subprocess.run([executable,'--query-gpu=name,driver_version,memory.total,memory.free,temperature.gpu',
                '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
            name,driver,total,free,temperature=[part.strip() for part in completed.stdout.splitlines()[0].split(',')]
            result['gpu']={'name':name,'driver':driver,'total_mib':float(total),
                           'free_mib':float(free),'temperature_c':float(temperature)}
            result['accelerator']='cuda'
        except (OSError,subprocess.SubprocessError,ValueError,IndexError):
            result['telemetry_error']='NVIDIA telemetry could not be read'
    if result['accelerator'] is None:
        try:
            from .device import resolve_device
            device=resolve_device('auto')
            result['accelerator']=device
            if device == 'mps':
                result['gpu']={'name':'Apple Metal Performance Shaders','backend':'mps',
                               'total_mib':None,'free_mib':None,'temperature_c':None}
        except (ImportError,ModuleNotFoundError,RuntimeError):
            result['accelerator']='unknown'
    _cached=result;_checked=time.monotonic()
    return result

def require_inference_headroom():
    from .execution_guard import execution_status, memory_reserve_bytes
    if execution_status()['paused']:
        raise RuntimeError('Inference is paused after a graphics crash; no GPU model is being loaded.')
    state=hardware_status();gpu=state['gpu'];accelerator=state.get('accelerator') or ('cuda' if gpu else None)
    if accelerator not in {'cuda','mps','cpu'}:
        raise RuntimeError('No supported local inference device is available.')
    if accelerator == 'cuda' and gpu is not None and gpu['temperature_c']>=82:
        raise RuntimeError('GPU is already at or above 82°C. Let the laptop cool before submitting a new run.')
    if accelerator == 'cuda' and gpu is not None and gpu['free_mib']<4096:
        raise RuntimeError('Less than 4 GiB GPU memory is available. Close other GPU workloads before retrying.')
    reserve=memory_reserve_bytes()
    if state['ram_available_bytes']<reserve:
        raise RuntimeError(f'Less than {reserve / 1024**3:.1f} GiB system memory is available for inference.')
    return state
