"""Regression coverage for interrupted and unresponsive workers; no GPU execution."""
import json
import inspect
import os
import subprocess
import sys
from pathlib import Path
import pytest

from neuroloop.db import Session, Run, initialize
from neuroloop import worker
from neuroloop.persistence import atomic_json


@pytest.fixture(autouse=True)
def isolated_process_telemetry(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from neuroloop import hardware, execution_guard
    monkeypatch.setattr(execution_guard, 'settings', lambda: SimpleNamespace(data=tmp_path))
    monkeypatch.setattr(hardware, 'hardware_status', lambda: {'gpu': {'temperature_c': 55}, 'ram_available_bytes': 8*1024**3})


def test_pressure_stops_owned_child_and_holds_followup(monkeypatch):
    from neuroloop import hardware, execution_guard
    identity=run_record()
    launch=subprocess.Popen
    children=[]
    def sleeping_child(*args, **kwargs):
        child=launch([sys.executable,'-c','import time; time.sleep(60)'],**kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(worker.subprocess, 'Popen', sleeping_child)
    monkeypatch.setattr(hardware, 'hardware_status', lambda: {'gpu': {'temperature_c': 85}, 'ram_available_bytes': 8*1024**3})
    worker.supervise_run(identity)
    assert children[0].poll() is not None
    assert execution_guard.execution_status()['paused']
    with Session() as db:
        row=db.get(Run,identity)
        assert row.status=='failed' and '82°C' in row.stop_reason
        assert row.result=={'saved':'keep-me'}


def run_record(**overrides):
    initialize()
    row = Run(project_id='recovery-test', status='running',
              config={'request': {'max_seconds': 30}}, result={'saved': 'keep-me'})
    for key, value in overrides.items():
        setattr(row, key, value)
    with Session.begin() as db:
        db.add(row); db.flush()
    return row.id


def test_restart_does_not_replay_crash_workload():
    identity = run_record()
    worker.recover_interrupted_runs()
    with Session() as db:
        row = db.get(Run, identity)
        assert row.status == 'failed' and row.finished_at
        assert row.result == {'saved': 'keep-me'}
        assert 'Submit a new run' in row.stop_reason


def test_completed_result_is_not_reclassified():
    identity = run_record(status='completed')
    worker.finish_interrupted(identity, 'unexpected exit')
    with Session() as db:
        assert db.get(Run, identity).status == 'completed'


def test_watchdog_terminates_stuck_owned_process(monkeypatch):
    identity = run_record(config={'request': {'max_seconds': 0.1}})
    launch = subprocess.Popen
    children = []
    def sleeping_child(*args, **kwargs):
        child = launch([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(worker.subprocess, 'Popen', sleeping_child)
    worker.supervise_run(identity)
    assert children[0].poll() is not None
    with Session() as db:
        row = db.get(Run, identity)
        assert row.status == 'failed' and 'time limit' in row.stop_reason
        assert row.result == {'saved': 'keep-me'}


def test_cancellation_terminates_owned_process(monkeypatch):
    identity = run_record(cancel_requested=1)
    launch = subprocess.Popen
    children = []
    def sleeping_child(*args, **kwargs):
        child = launch([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(worker.subprocess, 'Popen', sleeping_child)
    worker.supervise_run(identity)
    assert children[0].poll() is not None
    with Session() as db:
        assert db.get(Run, identity).status == 'cancelled'


def test_direct_worker_entry_honors_execution_hold(monkeypatch):
    from neuroloop import execution_guard
    identity = run_record()
    execution_guard.hold_execution('test hold', identity, {'gpu': None})
    monkeypatch.setattr(worker, 'execute_run', lambda _: pytest.fail('held work must not execute'))
    worker.process(identity)
    with Session() as db:
        row = db.get(Run, identity)
        assert row.status == 'failed' and 'paused' in row.stop_reason


def test_direct_evaluation_entry_honors_execution_hold(monkeypatch, tmp_path):
    import runpy
    import shutil
    from neuroloop import execution_guard, inference

    identity = run_record()
    execution_guard.hold_execution('test hold', identity, {'gpu': None})
    root = Path(__file__).resolve().parents[2]
    output = root / 'data/results' / f'direct-entry-hold-{tmp_path.name}'
    request = output / 'evaluation-request.json'
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(request, {'path': str(root / 'data/input.mp4'), 'kind': 'video',
                          'details': {}, 'config': {}, 'output': str(output)})
    called = []
    monkeypatch.setattr(inference, '_evaluate_in_process', lambda *args: called.append(True))
    monkeypatch.setattr(sys, 'argv', [str(root / 'scripts/evaluation_entry.py'), str(request)])
    try:
        with pytest.raises(SystemExit) as stopped:
            runpy.run_path(str(root / 'scripts/evaluation_entry.py'), run_name='__main__')
        assert stopped.value.code == 1
        assert called == []
        assert 'paused' in json.loads((output / 'process-error.json').read_text())['error']
    finally:
        shutil.rmtree(output, ignore_errors=True)


@pytest.mark.parametrize('relative_path', [
    'scripts/verify_real_tribe.py',
    'models/verify_assets.py',
    'tribev2-balanced-qv-local/verify_integration.py',
])
def test_direct_model_verifiers_require_headroom_before_model_imports(monkeypatch, relative_path):
    import runpy
    from neuroloop import hardware

    calls = []

    def blocked():
        calls.append(relative_path)
        raise RuntimeError('headroom gate blocked model imports')

    monkeypatch.setattr(hardware, 'require_inference_headroom', blocked)
    root = Path(__file__).resolve().parents[2]
    with pytest.raises(RuntimeError, match='headroom gate'):
        runpy.run_path(str(root / relative_path), run_name='__main__')
    assert calls == [relative_path]


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process-group ownership')
def test_timeout_terminates_run_descendants(monkeypatch):
    identity = run_record(config={'request': {'max_seconds': 0.1}})
    launch = subprocess.Popen
    children = []

    def grouped_child(*args, **kwargs):
        child = launch([
            sys.executable, '-c',
            'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"]); print(p.pid,flush=True); time.sleep(60)',
        ], stdout=subprocess.PIPE, text=True, start_new_session=True)
        children.append(child)
        return child

    monkeypatch.setattr(worker.subprocess, 'Popen', grouped_child)
    worker.supervise_run(identity)
    assert children[0].poll() is not None
    descendant_pid = int(children[0].stdout.readline().strip())
    import psutil
    try:
        descendant = psutil.Process(descendant_pid)
    except psutil.NoSuchProcess:
        # Group cleanup may reap the descendant before psutil constructs its
        # handle.  That is the strongest possible termination outcome.
        descendant = None
    if descendant is not None:
        try:
            descendant.wait(timeout=5)
        except psutil.NoSuchProcess:
            # The process exited between construction and wait().
            pass
        except psutil.TimeoutExpired:
            pytest.fail('run descendant survived supervisor timeout')
    with Session() as db:
        assert db.get(Run, identity).status == 'failed'


def test_invalid_atomic_update_preserves_previous_evidence(tmp_path):
    import pytest
    path = tmp_path / 'evidence.json'
    atomic_json(path, {'completed': True})
    with pytest.raises(ValueError):
        atomic_json(path, {'value': float('nan')})
    assert json.loads(path.read_text()) == {'completed': True}
    assert not list(tmp_path.glob('*.partial'))


def test_worker_prediction_load_closes_mmap(tmp_path):
    import numpy as np
    from types import SimpleNamespace
    path = tmp_path / 'prediction.npy'
    np.save(path, np.ones((2, 20484), dtype=np.float32), allow_pickle=False)
    loaded = worker.load_prediction(SimpleNamespace(prediction_path=str(path)))
    assert not isinstance(loaded, np.memmap)
    assert loaded.flags.owndata
    assert loaded.shape == (2, 20484)


def test_parent_cleanup_removes_only_evaluator_intermediates(tmp_path):
    output = tmp_path / 'result'
    output.mkdir()
    payload = output / 'evaluation-request.json'
    payload.write_text('{}', encoding='utf-8')
    (output / 'audio-16k.wav').write_bytes(b'audio')
    (output / 'presentation.mp4').write_bytes(b'video')
    (output / 'tsam').mkdir()
    (output / 'tsam' / 'frame.jpg').write_bytes(b'frame')
    evidence = output / 'evidence.json'
    evidence.write_text('{"keep": true}', encoding='utf-8')

    worker.inference._cleanup_evaluation_intermediates(output, payload)

    assert not payload.exists()
    assert not (output / 'audio-16k.wav').exists()
    assert not (output / 'presentation.mp4').exists()
    assert not (output / 'tsam').exists()
    assert evidence.read_text(encoding='utf-8') == '{"keep": true}'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX service process-group ownership')
def test_manage_shutdown_terminates_service_descendants():
    import psutil

    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    sys.path.insert(0, str(scripts))
    import manage
    from windows_job import OwnedJob

    child = subprocess.Popen([
        sys.executable, '-c',
        'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"]); print(p.pid,flush=True); time.sleep(60)',
    ], stdout=subprocess.PIPE, text=True, start_new_session=True)
    job = OwnedJob()
    job.add(child)
    descendant_pid = int(child.stdout.readline().strip())
    try:
        manage.stop_children({'fixture': child}, job)
        assert child.poll() is not None
        try:
            descendant = psutil.Process(descendant_pid)
        except psutil.NoSuchProcess:
            descendant = None
        if descendant is not None:
            try:
                descendant.wait(timeout=5)
            except psutil.NoSuchProcess:
                pass
            except psutil.TimeoutExpired:
                pytest.fail('service descendant survived managed shutdown')
        assert "start_new_session=os.name != 'nt'" in inspect.getsource(manage.serve)
    finally:
        job.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        try:
            remaining = psutil.Process(descendant_pid)
            if remaining.is_running():
                remaining.kill()
                remaining.wait(timeout=5)
        except psutil.NoSuchProcess:
            pass


@pytest.mark.skipif(os.name == 'nt', reason='POSIX service process-group ownership')
def test_manage_shutdown_cleans_descendants_after_group_leader_exits():
    import psutil

    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    sys.path.insert(0, str(scripts))
    import manage
    from windows_job import OwnedJob

    child = subprocess.Popen([
        sys.executable, '-c',
        'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"]); print(p.pid,flush=True); time.sleep(.2)',
    ], stdout=subprocess.PIPE, text=True, start_new_session=True)
    job = OwnedJob()
    job.add(child)
    descendant_pid = int(child.stdout.readline().strip())
    child.wait(timeout=5)
    try:
        manage.stop_children({'fixture': child}, job)
        try:
            descendant = psutil.Process(descendant_pid)
        except psutil.NoSuchProcess:
            descendant = None
        if descendant is not None:
            try:
                descendant.wait(timeout=5)
            except psutil.NoSuchProcess:
                pass
            except psutil.TimeoutExpired:
                pytest.fail('service descendant survived after its group leader exited')
    finally:
        job.close()
        try:
            remaining = psutil.Process(descendant_pid)
            if remaining.is_running():
                remaining.kill()
                remaining.wait(timeout=5)
        except psutil.NoSuchProcess:
            pass


def test_windows_job_closes_owned_process():
    import pytest
    if os.name != 'nt':
        pytest.skip('Windows service ownership')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from windows_job import OwnedJob
    import psutil
    job = OwnedJob()
    child = subprocess.Popen([sys.executable, '-c',
        'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); print(p.pid,flush=True); time.sleep(60)'],
        stdout=subprocess.PIPE, text=True)
    descendant = None
    try:
        job.add(child)
        descendant = psutil.Process(int(child.stdout.readline().strip()))
        assert child.poll() is None
        job.close()
        child.wait(timeout=5)
        descendant.wait(timeout=5)
        # Windows may report exit code zero for JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        # Completion within five seconds, rather than the child's 60-second sleep,
        # is the assertion that termination took effect.
        assert child.returncode is not None
    finally:
        job.close()
        if child.poll() is None:
            child.kill(); child.wait(timeout=5)
        if descendant and descendant.is_running():
            descendant.kill()
