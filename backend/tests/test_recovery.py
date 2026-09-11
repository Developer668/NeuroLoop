"""Regression coverage for interrupted and unresponsive workers; no GPU execution."""
import json
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


def test_invalid_atomic_update_preserves_previous_evidence(tmp_path):
    import pytest
    path = tmp_path / 'evidence.json'
    atomic_json(path, {'completed': True})
    with pytest.raises(ValueError):
        atomic_json(path, {'value': float('nan')})
    assert json.loads(path.read_text()) == {'completed': True}
    assert not list(tmp_path.glob('*.partial'))


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
