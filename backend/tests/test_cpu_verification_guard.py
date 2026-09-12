"""CPU-only diagnostic authorization never grants general GPU readiness."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('device,hidden,enabled', [
    ('cpu','-1',True), ('cpu','',True), ('cpu',None,False),
    ('cpu','0',False), ('auto','-1',False), ('cuda','-1',False),
])
def test_fresh_process_cpu_contract(tmp_path,device,hidden,enabled):
    hold=tmp_path/'inference-quarantine.json'
    hold.write_text('{"reason":"preserved graphics hold"}')
    env=os.environ.copy()
    env.update(NEUROLOOP_CPU_VERIFICATION='true',NEUROLOOP_INFERENCE_DEVICE=device)
    if hidden is None:
        env.pop('CUDA_VISIBLE_DEVICES',None)
    else:
        env['CUDA_VISIBLE_DEVICES']=hidden
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
    script='''
import json,sys
from pathlib import Path
from types import SimpleNamespace
from neuroloop import execution_guard as g
g.settings=lambda:SimpleNamespace(data=Path(sys.argv[1]))
print(json.dumps(g.execution_status()))
'''
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],env=env,capture_output=True,text=True,check=True,timeout=20)
    status=json.loads(result.stdout)
    assert status['paused'] is not enabled
    assert hold.read_text()=='{"reason":"preserved graphics hold"}'
    if enabled:
        assert status['execution_scope']=='cpu_only_verification'
        assert status['gpu_allowed'] is False


def test_torch_imported_before_guard_cannot_enable_override(tmp_path):
    env=os.environ.copy()
    env.update(NEUROLOOP_CPU_VERIFICATION='true',NEUROLOOP_INFERENCE_DEVICE='cpu',CUDA_VISIBLE_DEVICES='-1',PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result=subprocess.run([sys.executable,'-c',"import sys; sys.modules['torch']=object(); from neuroloop.execution_guard import cpu_verification_enabled; assert not cpu_verification_enabled()"],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_cpu_metadata_avoids_gpu_probe(monkeypatch):
    from neuroloop import hardware,execution_guard,device
    monkeypatch.setenv('NEUROLOOP_CPU_VERIFICATION','true')
    monkeypatch.setenv('NEUROLOOP_INFERENCE_DEVICE','cpu')
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES','-1')
    monkeypatch.setattr(execution_guard,'_CPU_VERIFICATION_BOOTSTRAPPED',True)
    monkeypatch.setattr(hardware,'_cached',None)
    monkeypatch.setattr(hardware.shutil,'which',lambda *_: pytest.fail('CPU mode must not probe NVIDIA'))
    state=hardware.hardware_status()
    assert state['accelerator']=='cpu' and state['gpu'] is None
    assert state['execution_scope']=='cpu_only_verification'
    assert device.resolve_device()=='cpu'
    for request in ('auto','cuda','mps'):
        with pytest.raises(RuntimeError,match='CPU verification'):
            device.resolve_device(request)
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES','0')
    assert not execution_guard.cpu_verification_enabled()


def test_cpu_pressure_preserves_original_quarantine(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from neuroloop import execution_guard as guard
    monkeypatch.setattr(guard,'cpu_verification_enabled',lambda:True)
    monkeypatch.setattr(guard,'settings',lambda:SimpleNamespace(data=tmp_path))
    hold=tmp_path/'inference-quarantine.json'
    hold.write_text('{"reason":"original GPU failure"}')
    guard.hold_execution('CPU RAM reserve','cpu-run',{'accelerator':'cpu'})
    assert hold.read_text()=='{"reason":"original GPU failure"}'
    assert json.loads((tmp_path/'cpu-verification-abort.json').read_text())['run_id']=='cpu-run'
    assert guard.memory_reserve_bytes()==4*1024**3
