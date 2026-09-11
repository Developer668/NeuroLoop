from types import SimpleNamespace
import pytest
from neuroloop import execution_guard as guard


@pytest.fixture
def guard_data(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'settings', lambda: SimpleNamespace(data=tmp_path))
    return tmp_path


def test_hold_survives_restart_and_corrupt_record(guard_data):
    assert guard.execution_status()['paused'] is False
    guard.hold_execution('test pressure', 'test-run', {'gpu': None})
    assert guard.execution_status()['reason'] == 'test pressure'
    with pytest.raises(RuntimeError, match='paused'):
        guard.require_execution_enabled()
    (guard_data/'inference-quarantine.json').write_text('broken')
    assert guard.execution_status()['paused'] is True


@pytest.mark.parametrize('temperature,available,expected', [(81,4,False),(82,4,True),(90,4,True),(65,2.9,True)])
def test_pressure_bounds(temperature,available,expected):
    result=guard.pressure_reason({'gpu':{'temperature_c':temperature},'ram_available_bytes':available*1024**3})
    assert bool(result) == expected


def test_missing_telemetry_fails_closed():
    assert guard.pressure_reason({'gpu':None})


def test_queue_entry_is_blocked_before_project_or_gpu_work(client,headers):
    from neuroloop.config import settings
    path=settings().data/'inference-quarantine.json'
    path.write_text('{"reason":"test graphics crash"}')
    try:
        from neuroloop import services
        from neuroloop.schemas import RunCreate
        with pytest.raises(services.DomainError, match='paused'):
            services.create_run(RunCreate(project_id='not-loaded'))
        assert client.get('/api/capabilities',headers=headers).json()['execution']['paused']
        response=client.post('/api/neuro/command',headers=headers,json={'command':'/status'})
        assert response.status_code == 200
        assert 'paused after a graphics crash' in response.json()['message']
    finally:
        path.unlink()
