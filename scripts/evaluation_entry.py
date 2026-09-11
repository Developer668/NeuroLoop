"""Single-evaluation child. The run supervisor owns this process lifetime."""
import json,shutil,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.persistence import atomic_json
from neuroloop.execution_guard import require_execution_enabled

if __name__=='__main__':
    request=Path(sys.argv[1]).resolve()
    if not request.is_relative_to(ROOT/'data/results'):
        raise ValueError('Evaluation request is outside managed results')
    arguments=json.loads(request.read_text(encoding='utf-8'))
    output=Path(arguments['output']).resolve()
    if not output.is_relative_to(ROOT/'data/results'):
        raise ValueError('Evaluation output is outside managed results')
    def progress(stage):print('NEUROLOOP_STAGE:'+json.dumps(stage),flush=True)
    try:
        # Keep the executable entry point fail-closed even when it is invoked
        # directly instead of through the worker supervisor.
        require_execution_enabled()
        from neuroloop.inference import _evaluate_in_process
        _evaluate_in_process(Path(arguments['path']),arguments['kind'],arguments['details'],arguments['config'],output,progress)
    except Exception as exc:
        atomic_json(output/'process-error.json',{'error':type(exc).__name__+': '+str(exc)[:1200]})
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        # These are evaluator-owned intermediates, not published evidence.
        for name in ('audio-16k.wav','presentation.mp4'):
            (output/name).unlink(missing_ok=True)
        shutil.rmtree(output/'tsam', ignore_errors=True)
        request.unlink(missing_ok=True)
