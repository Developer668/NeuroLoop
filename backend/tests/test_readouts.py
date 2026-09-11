import json
import numpy as np
import pytest
from pydantic import ValidationError
from neuroloop.schemas import RunCreate
from neuroloop import anatomy

def test_tsam_requires_explicit_research_acknowledgement():
    with pytest.raises(ValidationError, match='Acknowledge'):
        RunCreate(project_id='project', include_tsam=True)
    assert RunCreate(project_id='project', include_tsam=True, tsam_research_acknowledged=True).include_tsam

def test_anatomical_means_respect_hemisphere_and_vertex_order(monkeypatch):
    mapping=[1]*5000+[2]*5242
    monkeypatch.setattr(anatomy,'atlas',lambda:({'atlas':'test','mesh':'fsaverage5',
        'left':mapping,'right':mapping,'labels':['Unknown','first','second']},'test-hash'))
    response=np.zeros((2,20484))
    response[:,:5000]=2
    response[:,10242:15242]=-3
    result=anatomy.summarize_regions(response)
    values={r['id']:r for r in result['regions']}
    assert values['left:1']['mean']==[2,2]
    assert values['right:1']['mean']==[-3,-3]
    assert values['right:2']['mean']==[0,0]
    assert values['left:1']['vertices']==5000
    with pytest.raises(ValueError): anatomy.summarize_regions(np.zeros((2,64984)))

def test_client_configuration_has_expiring_token_and_no_cache(client,authed):
    response=client.get('/api/connections/mcp/config',headers=authed)
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    config=response.json()['mcpServers']['neuroloop']
    assert config['url']=='http://127.0.0.1:8010/mcp/'
    assert config['headers']['Authorization']!=authed['Authorization']
    from neuroloop.auth import verify_token
    assert verify_token(config['headers']['Authorization'][7:])

def test_hardware_preflight_refuses_heat_and_memory_pressure(monkeypatch):
    from neuroloop import hardware
    state={'gpu':{'temperature_c':84,'free_mib':9000},'ram_available_bytes':12*1024**3}
    monkeypatch.setattr(hardware,'hardware_status',lambda:state)
    with pytest.raises(RuntimeError,match='cool'): hardware.require_inference_headroom()
    state['gpu']['temperature_c']=60;state['gpu']['free_mib']=1024
    with pytest.raises(RuntimeError,match='4 GiB'): hardware.require_inference_headroom()
    state['gpu']['free_mib']=9000
    assert hardware.require_inference_headroom()==state

def test_preferences_are_persisted_and_validated(client,authed):
    value={'display_name':'Researcher','workspace_name':'Creative studio','reduced_motion':True}
    assert client.put('/api/preferences',headers=authed,json=value).status_code==200
    assert client.get('/api/preferences',headers=authed).json()==value
    assert client.put('/api/preferences',headers=authed,json={**value,'workspace_name':''}).status_code==422
