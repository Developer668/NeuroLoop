import io
import numpy as np
import pytest
from PIL import Image
from neuroloop.readout import validate_response,similarity,summarize,compare_references
from neuroloop.schemas import RunCreate,TimedWord,CreativeCreate
from neuroloop import policy

def image_bytes(color=(90,60,60)):
    output=io.BytesIO();Image.new('RGB',(320,180),color).save(output,format='PNG');return output.getvalue()

def upload(client,headers,color=(90,60,60),name='test.png'):
    response=client.post('/api/assets',headers=headers,files={'file':(name,image_bytes(color),'image/png')})
    assert response.status_code==201,response.text
    return response.json()

def project(client,headers,original,refs=None):
    response=client.post('/api/projects',headers=headers,json={'name':'Contract test','asset_id':original['id'],'reference_ids':refs or []})
    assert response.status_code==201,response.text
    return response.json()

def test_authentication_is_required(client):
    for path in ['/api/dashboard','/api/capabilities','/api/policy','/api/geometry','/api/docs']:
        assert client.get(path).status_code==401
    assert client.get('/health').status_code==200

def test_wrong_token_rejected(client):
    assert client.get('/api/capabilities',headers={'Authorization':'Bearer invalid'}).status_code==401

def test_local_auth_requires_origin_and_header(client):
    assert client.post('/auth/local').status_code==403
    assert client.post('/auth/local',headers={'Origin':'https://evil.example','X-NeuroLoop-Local':'browser'}).status_code==403
    response=client.post('/auth/local',headers={'Origin':'http://localhost:3010','X-NeuroLoop-Local':'browser'})
    assert response.status_code==200,response.text
    assert client.get('/api/capabilities',headers={'Authorization':'Bearer '+response.json()['token']}).status_code==200

def test_forged_host_rejected_for_local_login(client):
    response=client.post('/auth/local',headers={'Origin':'http://localhost:3010','Host':'evil.example','X-NeuroLoop-Local':'browser'})
    assert response.status_code==403

def test_upload_and_managed_asset(client,headers):
    asset=upload(client,headers)
    assert asset['kind']=='image' and asset['details']['width']==320
    assert 'path' not in asset
    assert len(asset['sha256'])==64
    assert client.get('/api/assets/'+asset['id']+'/content',headers=headers).content==image_bytes()
    assert client.get('/api/assets/'+asset['id']+'/preview',headers=headers).status_code==200

def test_corrupt_and_empty_uploads(client,headers):
    assert client.post('/api/assets',headers=headers,files={'file':('invalid.exe',b'abc')}).status_code==415
    assert client.post('/api/assets',headers=headers,files={'file':('empty.txt',b'')}).status_code==400
    response=client.post('/api/assets',headers=headers,files={'file':('invalid.png',b'not an image')})
    assert response.status_code in {400,422}

def test_text_has_no_fake_preview_image(client,headers):
    asset=client.post('/api/assets',headers=headers,files={'file':('brief.txt',b'Honest creative research.')}).json()
    assert asset['details']['preview_text']=='Honest creative research.'
    assert 'preview' not in asset['details']
    assert client.get('/api/assets/'+asset['id']+'/preview',headers=headers).status_code==404

def test_transcript_matches_source_text(client,headers):
    asset=client.post('/api/assets',headers=headers,files={'file':('words.txt',b'Hello world')}).json()
    url='/api/assets/'+asset['id']+'/transcript'
    assert client.put(url,headers=headers,json={'words':[{'text':'Different','start':0,'end':1}]}).status_code==422
    result=client.put(url,headers=headers,json={'words':[{'text':'Hello','start':0,'end':.8},{'text':'world','start':.9,'end':1.5}]})
    assert result.status_code==200,result.text
    assert len(result.json()['details']['transcript'])==2

def test_unknown_asset_rejected(client,headers):
    assert client.post('/api/projects',headers=headers,json={'name':'Unknown','asset_id':'missing'}).status_code==400

def test_duplicate_original_reference(client,headers):
    asset=upload(client,headers)
    assert client.post('/api/projects',headers=headers,json={'name':'Invalid','asset_id':asset['id'],'reference_ids':[asset['id']]}).status_code==400

def test_static_image_requires_explicit_permission(client,headers):
    asset=upload(client,headers);p=project(client,headers,asset)
    assert client.post('/api/runs',headers=headers,json={'project_id':p['id']}).status_code==400

def test_run_idempotency_and_cancellation(client,headers):
    asset=upload(client,headers);p=project(client,headers,asset)
    body={'project_id':p['id'],'allow_static_presentation':True};h={**headers,'Idempotency-Key':'repeat-contract-test'}
    first=client.post('/api/runs',headers=h,json=body);assert first.status_code==202,first.text
    second=client.post('/api/runs',headers=h,json=body);assert second.status_code==202
    assert first.json()['id']==second.json()['id']
    assert client.post('/api/runs',headers=h,json={**body,'max_evaluations':5}).status_code==400
    rid=first.json()['id'];cancel=client.post('/api/runs/'+rid+'/cancel',headers=headers)
    assert cancel.status_code==200 and cancel.json()['status']=='cancelled'
    assert client.get('/api/runs/'+rid+'/export',headers=headers).status_code==409

def test_comparison_requires_reference_budget(client,headers):
    original=upload(client,headers,(100,20,20));reference=upload(client,headers,(20,20,100));p=project(client,headers,original,[reference['id']])
    response=client.post('/api/runs',headers=headers,json={'project_id':p['id'],'mode':'optimize','allow_static_presentation':True,'max_evaluations':1})
    assert response.status_code==400

def test_duplicate_reference_bytes_rejected(client,headers):
    original=upload(client,headers);same=upload(client,headers);p=project(client,headers,original,[same['id']])
    assert client.post('/api/runs',headers=headers,json={'project_id':p['id'],'allow_static_presentation':True}).status_code==400

def test_no_headline_edit_on_flattened_input(client,headers):
    a=upload(client,headers,(31,41,51));b=upload(client,headers,(51,61,71));p=project(client,headers,a,[b['id']])
    response=client.post('/api/runs',headers=headers,json={'project_id':p['id'],'mode':'optimize','allow_static_presentation':True,'operators':['headline_early']})
    assert response.status_code==400

def test_rejects_unsupported_constraints(client,headers):
    a=upload(client,headers);p=client.post('/api/projects',headers=headers,json={'name':'Impossible requirement','asset_id':a['id'],'constraints':{'purchase_probability':.95}}).json()
    response=client.post('/api/runs',headers=headers,json={'project_id':p['id'],'allow_static_presentation':True})
    assert response.status_code==400

def test_no_fabricated_evidence_on_missing_result(client,headers):
    assert client.get('/api/evaluations/missing',headers=headers).status_code==404
    assert client.get('/api/evaluations/missing/frame',headers=headers).status_code==404
    assert client.post('/api/compare',headers=headers,json={'evaluation_ids':['missing-a','missing-b']}).status_code==404

@pytest.mark.parametrize('data',[np.zeros((20484,)),np.zeros((1,8)),np.empty((0,20484)),np.full((2,20484),np.nan)])
def test_invalid_cortical_arrays_are_rejected(data):
    with pytest.raises(ValueError):validate_response(data)

def test_reference_metric_is_not_a_probability():
    # Synthetic arrays are mathematical unit fixtures, never app inference output.
    x=np.random.default_rng(2).normal(size=(4,20484))
    assert similarity(x,x)==pytest.approx(1)
    assert similarity(x,-x)==pytest.approx(-1)
    assert compare_references(x,[('opposite',-x)])['value']<0
    assert summarize(x,[0,1,2,3])['shape']==[4,20484]
    with pytest.raises(ValueError):summarize(x,[0])
    with pytest.raises(ValueError):similarity(np.zeros((4,20484)),x)

def test_schema_rejects_unknown_parameters():
    with pytest.raises(ValueError):RunCreate(project_id='x',invent_scores=True)
    with pytest.raises(ValueError):TimedWord(text='x',start=2,end=1)
    with pytest.raises(ValueError):RunCreate(project_id='x',max_evaluations=0)

def test_policy_updates_only_recorded_context():
    assert policy.choose('unseen',['contrast_up'],set(),'seed')['attempts']==0
    policy.record('known','contrast_up',.05,10,.005)
    outcome=policy.choose('known',['contrast_up'],set(),'seed')
    assert outcome['successes']==1 and outcome['failures']==0
    assert policy.choose('other',['contrast_up'],set(),'seed')['attempts']==0
    assert policy.choose('known',['contrast_up'],{'contrast_up'},'seed') is None

def test_real_renderer_creates_valid_video(client,headers):
    source=upload(client,headers,(144,120,101))
    response=client.post('/api/creatives',headers=headers,json={'asset_id':source['id'],'headline':'A controlled composition','subline':'Test fixture, not a campaign','duration':5,'headline_start':1,'aspect':'landscape'})
    assert response.status_code==201,response.text
    data=response.json();assert data['kind']=='video' and abs(data['details']['duration']-5)<.15
    assert data['details']['has_audio'] is False
    assert data['details']['composition']['headline']=='A controlled composition'
    assert client.get('/api/assets/'+data['id']+'/content',headers=headers).status_code==200
