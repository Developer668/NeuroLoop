import io,json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from neuroloop.readout import validate_response,fingerprint,similarity,compare_references
from neuroloop.schemas import TimedWord,RunCreate
from neuroloop import policy


def image_upload(client,auth,name='fixture.png',shade=(120,100,90)):
    output=io.BytesIO();Image.new('RGB',(64,48),shade).save(output,format='PNG')
    response=client.post('/api/assets',headers=auth,files={'file':(name,output.getvalue(),'image/png')})
    assert response.status_code==201,response.text
    return response.json()

def project(client,auth,original,refs=None,constraints=None):
    response=client.post('/api/projects',headers=auth,json={'name':'Test project','asset_id':original,'reference_ids':refs or [],'constraints':constraints or {}})
    assert response.status_code==201,response.text
    return response.json()

def test_response_rejects_wrong_shape():
    with pytest.raises(ValueError):validate_response(np.zeros((4,10)))

def test_response_rejects_nan():
    x=np.zeros((2,20484));x[0,0]=np.nan
    with pytest.raises(ValueError):validate_response(x)

def test_degenerate_comparison_rejected():
    with pytest.raises(ValueError):fingerprint(np.ones((2,20484)))

def test_identical_response_has_unit_similarity():
    x=np.random.default_rng(1).normal(size=(6,20484))
    assert similarity(x,x)==pytest.approx(1)

def test_constant_spatial_offset_does_not_change_metric():
    x=np.random.default_rng(2).normal(size=(6,20484))
    assert similarity(x,x+10)==pytest.approx(1)

def test_opposite_pattern_has_negative_similarity():
    x=np.random.default_rng(3).normal(size=(6,20484))
    assert similarity(x,-x)==pytest.approx(-1)

def test_reference_scores_preserved_separately():
    x=np.random.default_rng(4).normal(size=(6,20484))
    result=compare_references(x,[('a',x),('b',-x)])
    assert len(result['per_reference'])==2
    assert result['value']==pytest.approx(0)
    assert result['evidence_type']=='model-reference-similarity'

def test_words_need_valid_order():
    with pytest.raises(ValueError):TimedWord(text='hello',start=2,end=1)

def test_run_rejects_arbitrary_operator():
    with pytest.raises(ValueError):RunCreate(project_id='x',operators=['execute_shell'])

def test_authentication_required(client):
    assert client.get('/api/dashboard').status_code==401
    assert client.get('/api/dashboard',headers={'Authorization':'Bearer incorrect'}).status_code==401
    assert client.get('/health').status_code==200

def test_local_session_rejects_foreign_origin(client):
    assert client.post('/auth/local',headers={'Origin':'https://untrusted.example','X-NeuroLoop-Local':'browser'}).status_code==403

def test_local_session_works_without_exposing_master_token(client):
    r=client.post('/auth/local',headers={'Origin':'http://localhost:3010','X-NeuroLoop-Local':'browser'})
    assert r.status_code==200
    assert r.json()['token']!='test-only-not-a-real-secret-00000000000'
    assert client.get('/api/dashboard',headers={'Authorization':'Bearer '+r.json()['token']}).status_code==200

def test_unknown_upload_type_rejected(client,authed):
    assert client.post('/api/assets',headers=authed,files={'file':('script.exe',b'hello')}).status_code==415

def test_upload_empty_rejected(client,authed):
    assert client.post('/api/assets',headers=authed,files={'file':('empty.txt',b'')}).status_code==400

def test_image_upload_is_real_and_private(client,authed):
    item=image_upload(client,authed)
    assert item['details']['width']==64 and 'path' not in item
    assert client.get('/api/assets/'+item['id']+'/content').status_code==401
    assert client.get('/api/assets/'+item['id']+'/content',headers=authed).content.startswith(b'\x89PNG')

def test_original_cannot_be_reference(client,authed):
    item=image_upload(client,authed)
    r=client.post('/api/projects',headers=authed,json={'name':'Invalid','asset_id':item['id'],'reference_ids':[item['id']]})
    assert r.status_code==400

def test_image_needs_explicit_presentation_consent(client,authed):
    item=image_upload(client,authed);p=project(client,authed,item['id'])
    r=client.post('/api/runs',headers=authed,json={'project_id':p['id']})
    assert r.status_code==400 and 'experimental' in r.json()['detail'].lower()

def test_idempotent_run_and_cancellation(client,authed):
    item=image_upload(client,authed);p=project(client,authed,item['id'])
    payload={'project_id':p['id'],'allow_static_presentation':True}
    headers={**authed,'Idempotency-Key':'test-idempotency'}
    a=client.post('/api/runs',headers=headers,json=payload);b=client.post('/api/runs',headers=headers,json=payload)
    assert a.status_code==202 and a.json()['id']==b.json()['id']
    changed=client.post('/api/runs',headers=headers,json={**payload,'max_evaluations':5})
    assert changed.status_code==400
    cancelled=client.post('/api/runs/'+a.json()['id']+'/cancel',headers=authed)
    assert cancelled.json()['status']=='cancelled'

def test_budget_must_cover_references(client,authed):
    a=image_upload(client,authed,shade=(90,80,70));b=image_upload(client,authed,shade=(100,90,80));p=project(client,authed,a['id'],[b['id']])
    r=client.post('/api/runs',headers=authed,json={'project_id':p['id'],'mode':'optimize','allow_static_presentation':True,'max_evaluations':1})
    assert r.status_code==400 and 'budget' in r.json()['detail'].lower()

def test_duplicate_content_reference_rejected(client,authed):
    a=image_upload(client,authed);b=image_upload(client,authed);p=project(client,authed,a['id'],[b['id']])
    r=client.post('/api/runs',headers=authed,json={'project_id':p['id'],'allow_static_presentation':True})
    assert r.status_code==400

def test_unsupported_constraints_rejected(client,authed):
    a=image_upload(client,authed);p=project(client,authed,a['id'],constraints={'predict_purchase_probability':True})
    r=client.post('/api/runs',headers=authed,json={'project_id':p['id'],'allow_static_presentation':True})
    assert r.status_code==400 and 'Unsupported constraints' in r.json()['detail']

def test_full_creative_constraint_contract_reaches_worker_queue(client,authed):
    a=image_upload(client,authed)
    p=project(client,authed,a['id'],constraints={
        'required_copy':['Keep exact copy'],
        'required_logo':'logo-v1',
        'required_objects':['product-pack'],
        'expected_width':64,
        'expected_height':48,
        'preserve_dimensions':True,
        'require_audio':False,
    })
    r=client.post('/api/runs',headers=authed,json={
        'project_id':p['id'],
        'allow_static_presentation':True,
    })
    assert r.status_code==202,r.text
    assert r.json()['config']['project_snapshot']['constraints']==p['constraints']

def test_never_invent_missing_emotion_outputs(client,authed):
    data=client.get('/api/capabilities',headers=authed).json()
    assert data['kragel']['status']=='missing_assets'
    assert data['tsam']['status']=='missing_weights'
    assert data['training'] is False

def test_missing_geometry_returns_unavailable(client,authed):
    assert client.get('/api/geometry',headers=authed).status_code==503

def test_policy_is_reproducible_and_excludes_completed():
    a=policy.choose('test-context',['contrast_up','contrast_down'],set(),'fixed-seed')
    b=policy.choose('test-context',['contrast_up','contrast_down'],set(),'fixed-seed')
    assert a==b
    assert policy.choose('test-context',['contrast_up'],{'contrast_up'},'x') is None

def test_policy_updates_only_statistics():
    policy.record('unit-context','contrast_up',0.02,3,0.005)
    policy.record('unit-context','contrast_up',-0.01,2,0.005)
    row=next(x for x in policy.history() if x['context']=='unit-context')
    assert row['attempts']==2 and row['successes']==1 and row['failures']==1
