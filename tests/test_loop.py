"""CPU-only tests. Synthetic model answers live ONLY in this test module."""
from pathlib import Path
import json
import math
import pytest
import httpx
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from fastapi.testclient import TestClient
from neuroloop_app.config import Settings
from neuroloop_app.domain import *
from neuroloop_app.db import Store, Job, Run, Trace
from neuroloop_app.engine import LoopEngine, DomainError
from neuroloop_app.storage import ObjectStore, StorageError, inspect_media
from neuroloop_app.sponsors import TypeSafeKernel, WandBReasoner, ProviderFailure
from neuroloop_app.api import create_app

@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, operator_token='o'*40, worker_token='w'*40,
                    local_bootstrap_token='b'*40, signing_key='s'*40)

@pytest.fixture
def engine(settings):
    store=Store(settings); store.initialize()
    return LoopEngine(store, ObjectStore(settings))

P={'model':'TEST_ONLY','version':'fixture-v1','configuration_hash':'test-config'}

def campaign(engine):
    return engine.create_campaign(CampaignSpec(title='CPU test fixture',brief='A test image, not a real advertisement.',
                brand=BrandSpec(name='Test fixture'),media_kind='image',aspect_ratio='1:1'))

def begin(engine, **kwargs):
    c=campaign(engine)
    engine.register_worker(WorkerHello(worker_id='test-worker', capabilities={k:{'status':'READY','cost_ceiling_usd':0.01} for k in ['reasoner','typesafe','generate_image','evaluate_vision']}))
    config=RunConfig(initial_candidates=2,beam_width=2,branch_factor=2,optional_evaluators=[],**kwargs)
    r=engine.start(c['id'],StartRun(config=config),'start-test')
    return c,r

def complete(engine,job,result):
    return engine.complete(job['id'],CompleteJob(worker_id='test-worker',lease_token=job['lease_token'],result=result))

def review_for(payload, choice="APPROVE"):
    return {"plan_hash":digest(payload["plan"]), "choice":choice, "confidence":.95, "model":"TEST_ONLY",
        "raw_response":{"model":"TEST_ONLY", "answers":{"plan_gate":{"type":"choice","choice":choice,"confidence":.95,
        "probabilities":{"APPROVE":1.0 if choice=="APPROVE" else 0.0,"REJECT":0.0 if choice=="APPROVE" else 1.0}}}}}


def optimization_for(evaluations):
    e=next(e for e in evaluations if e["evaluator"]=="vision")
    return {"observation":{"evaluation_id":e["id"],"response_metric":"creative_quality","value":e["result"]["scores"]["creative_quality"]["value"]},
        "creative_evidence":{"evaluation_id":e["id"],"description":"TEST_ONLY"},"explanation":"Test hypothesis", "confidence":.8,
        "target":"layout","instruction":"Reduce clutter","expected_metric":"creative_quality","expected_direction":"increase"}


def approve_pending(engine):
    j=engine.claim('test-worker'); assert j['kind']=='REVIEW_PLAN'
    complete(engine,j,review_for(j['payload']))


def plan_for(job):
    plans=[]
    for slot in job['payload']['candidate_slots']:
        parent=slot['parent_creative_id']; evidence=[]
        if parent:
            p=next(x for x in job['payload']['parents'] if x['creative']['id']==parent)
            evidence=[x['id'] for x in p['evidence']['evaluations']]
        plans.append({'parent_creative_id':parent,'prompt':'Test-only model contract','strategy':'TEST_ONLY','edit_intent':{
            'primary_goal':'test lineage','preserve':['product_identity'],'reasoning_evidence_ids':evidence,'optimization':optimization_for(p['evidence']['evaluations']) if parent else None}})
    return {'summary':'Synthetic response only in tests','model':'TEST_ONLY','candidates':plans}

def generated(engine,job,tmp_path,shade=50):
    path=tmp_path/(job['id']+'.png'); Image.new('RGB',(64,64),(shade,shade,shade)).save(path)
    a=engine.add_asset(job['campaign_id'],path,'fixture.png',job_id=job['id'],worker_id='test-worker',lease_token=job['lease_token'],upload_key='test-output')
    return {'asset_id':a['id'],'provenance':P,'gpu_seconds':0,'cost_usd':0}

def evaluated(job,value=.5,version='fixture-v1',fail=False):
    return {'evaluator':'vision','status':'SUCCEEDED','provenance':{**P,'version':version},
        'scores':{'creative_quality':{'value':value,'source':'TEST_ONLY','meaning':'Synthetic test score, not real evaluation'}},
        'constraints':[{'name':n,'status':'FAIL' if fail else 'PASS','evidence':'TEST_ONLY'} for n in ['product_identity','approved_claims_only','no_prohibited_claims']], 'cost_usd':0}

@pytest.mark.parametrize('delivery,unknown,repairs', [('GENERATED_MEDIA',False,True), ('PROVIDER_REFUSAL',False,False), ('GENERATED_MEDIA',True,False)])
def test_constraint_repair_preserves_failed_parent_and_review_gate(engine,tmp_path,delivery,unknown,repairs):
    c,r=begin(engine,max_rounds=2,max_candidates=4)
    complete(engine,(j:=engine.claim('test-worker')),plan_for(j))
    approve_pending(engine)
    for _ in range(2):
        j=engine.claim('test-worker'); complete(engine,j,generated(engine,j,tmp_path))
    for _ in range(2):
        j=engine.claim('test-worker'); result=evaluated(j,fail=True)
        result['observations']={'media_delivery':delivery}
        if unknown: result['constraints'][0]['status']='UNKNOWN'
        complete(engine,j,result)
    snapshot=engine.snapshot(r['id'])
    assert all(c['status']=='INVALID' for c in snapshot['creatives'])
    assert snapshot['run']['champion_id'] is None
    if not repairs:
        assert snapshot['run']['state']=='READY_FOR_REVIEW'
        return
    j=engine.claim('test-worker')
    assert j['kind']=='PLAN' and j['payload']['constraint_repair'] is True
    assert all(not p['evidence']['eligible'] for p in j['payload']['parents'])
    complete(engine,j,plan_for(j))
    review=engine.claim('test-worker')
    assert review['kind']=='REVIEW_PLAN'
    complete(engine,review,review_for(review['payload'],'REJECT'))
    assert engine.snapshot(r['id'])['run']['stats']['generation_count']==2

def advance_to_decision(engine,tmp_path):
    count=0
    while count<20:
        j=engine.claim('test-worker'); assert j is not None
        if j['kind']=='DECIDE': return j
        if j['kind']=='PLAN': complete(engine,j,plan_for(j))
        elif j['kind']=='REVIEW_PLAN': complete(engine,j,review_for(j['payload']))
        elif j['kind']=='GENERATE': complete(engine,j,generated(engine,j,tmp_path,30+count))
        elif j['kind']=='EVALUATE': complete(engine,j,evaluated(j,.45+count*.01))
        count+=1
    raise AssertionError('Decision not reached')

def decision(job,action='REGENERATE',confidence=.9):
    return {'decision':action,'selected_creative_ids':job['payload']['allowed_creative_ids'][:2],
            'strategy':'TEST_ONLY','confidence':confidence,'reason_codes':['TEST_ONLY'], 'raw_response':{'fixture':True},'model':'TEST_ONLY'}

def test_decision_cannot_offer_ready_below_quality_target(engine,tmp_path):
    begin(engine,quality_threshold=.99)
    job=advance_to_decision(engine,tmp_path)
    assert 'READY_FOR_DEPLOYMENT' not in job['payload']['allowed_actions']
    with pytest.raises(DomainError,match='unauthorized action'):
        complete(engine,job,decision(job,'READY_FOR_DEPLOYMENT'))

def test_child_cannot_cite_creative_id_as_evaluation(engine,tmp_path):
    begin(engine)
    choose=advance_to_decision(engine,tmp_path)
    complete(engine,choose,decision(choose))
    job=engine.claim('test-worker'); plan=plan_for(job)
    plan['candidates'][0]['edit_intent']['reasoning_evidence_ids'].append(plan['candidates'][0]['parent_creative_id'])
    with pytest.raises(DomainError,match='not creative or asset IDs'):
        complete(engine,job,plan)
    assert not any(j['kind']=='REVIEW_PLAN' and j['payload']['round']==1 for j in engine.snapshot(job['run_id'])['jobs'])

def test_plan_correction_does_not_reroll_valid_rejected_plan(engine):
    _,run=begin(engine)
    job=engine.claim('test-worker'); complete(engine,job,plan_for(job))
    review=engine.claim('test-worker'); complete(engine,review,review_for(review['payload'],'REJECT'))
    with pytest.raises(DomainError,match='review cannot be bypassed'):
        engine.correct_invalid_plan(run['id'])

@pytest.mark.parametrize('online', [True, False])
def test_optional_evaluator_routes_to_separate_online_worker(engine, tmp_path, online):
    from neuroloop_app.db import Worker
    _, run = begin(engine)
    engine.register_worker(WorkerHello(worker_id='research-worker', capabilities={'evaluate_tsam': {'status': 'READY'}}))
    with engine.store.transaction() as session:
        row = session.get(Run, run['id'])
        row.snapshot = {**row.snapshot, 'config': {**row.snapshot['config'], 'optional_evaluators': ['tsam']}}
        if not online:
            session.get(Worker, 'research-worker').heartbeat_at = 0
    for _ in range(10):
        job = engine.claim('test-worker')
        if job is None or job['kind'] == 'DECIDE':
            break
        if job['kind'] == 'PLAN': complete(engine, job, plan_for(job))
        elif job['kind'] == 'REVIEW_PLAN': complete(engine, job, review_for(job['payload']))
        elif job['kind'] == 'GENERATE': complete(engine, job, generated(engine, job, tmp_path))
        elif job['kind'] == 'EVALUATE': complete(engine, job, evaluated(job))
    with engine.store.transaction() as session:
        queued = list(session.scalars(select(Job).where(Job.run_id == run['id'], Job.capability == 'evaluate_tsam')))
        assert bool(queued) is online
    if online:
        assert engine.claim('research-worker')['capability'] == 'evaluate_tsam'


def test_real_state_machine_two_rounds_preserves_all_assets(engine,tmp_path):
    c,r=begin(engine,max_rounds=2)
    first=advance_to_decision(engine,tmp_path)
    complete(engine,first,decision(first))
    second=advance_to_decision(engine,tmp_path)
    complete(engine,second,decision(second))
    snap=engine.snapshot(r['id'])
    assert snap['run']['state']=='READY_FOR_REVIEW'
    assert snap['run']['stop_reason']=='GENERATION_ROUND_LIMIT'
    assert len(snap['creatives'])==6
    assert len({x['output_asset_id'] for x in snap['creatives']})==6
    parents={x['id']:x for x in snap['creatives']}
    for child in snap['creatives'][2:]:
        assert child['parent_id'] in parents
        assert parents[child['parent_id']]['output_asset_id'] in child['input_asset_ids']
        assert child['plan']['edit_intent']['reasoning_evidence_ids']
    assert len(engine.learning()['observations'])>=4
    assert all(t['parent_id']==r['id'] for t in snap['traces'] if t['id']!=r['id'])

def test_unknown_provider_is_not_a_fake_success(engine):
    c=campaign(engine); r=engine.start(c['id'],StartRun(),'idem')
    engine.register_worker(WorkerHello(worker_id='empty',capabilities={}))
    assert engine.claim('empty') is None
    assert engine.snapshot(r['id'])['run']['state']=='PLANNING'
    assert engine.snapshot(r['id'])['creatives']==[]

def test_idempotency_and_cross_campaign_references(engine,tmp_path):
    c=campaign(engine); body=StartRun(); r=engine.start(c['id'],body,'same')
    assert engine.start(c['id'],body,'same')['id']==r['id']
    with pytest.raises(DomainError): engine.start(c['id'],StartRun(config=RunConfig(beam_width=1)),'same')
    path=tmp_path/'image.png'; Image.new('RGB',(10,10)).save(path)
    a=engine.add_asset(c['id'],path,'image.png'); other=campaign(engine)
    with pytest.raises(DomainError): engine.start(other['id'],StartRun(reference_asset_ids=[a['id']]),'cross')

def test_generation_lease_loss_is_uncertain_not_autoretried(engine,tmp_path):
    c,r=begin(engine)
    p=engine.claim('test-worker'); complete(engine,p,plan_for(p))
    approve_pending(engine)
    j=engine.claim('test-worker')
    with engine.store.transaction() as s: s.get(Job,j['id']).lease_until=0
    engine.recover_expired(); snap=engine.snapshot(r['id'])
    assert snap['run']['state']=='NEEDS_ATTENTION'
    assert next(x for x in snap['jobs'] if x['id']==j['id'])['status']=='UNCERTAIN'
    assert engine.claim('test-worker') is None
    with pytest.raises(DomainError): engine.resume(r['id'])
    # Late receipt from the ORIGINAL lease recovers safely, without new inference.
    complete(engine,j,generated(engine,j,tmp_path))
    assert engine.snapshot(r['id'])['run']['state']=='GENERATING'

def test_cancel_rejects_late_completion(engine):
    c,r=begin(engine); j=engine.claim('test-worker'); engine.cancel(r['id'])
    with pytest.raises(DomainError): complete(engine,j,plan_for(j))
    assert engine.snapshot(r['id'])['run']['state']=='CANCELLED'

def test_completed_response_immutable_and_replayed(engine):
    c,r=begin(engine); j=engine.claim('test-worker'); p=plan_for(j)
    complete(engine,j,p); complete(engine,j,p)
    p['summary']='changed'
    with pytest.raises(DomainError): complete(engine,j,p)
    approve_pending(engine)
    assert len(engine.snapshot(r['id'])['creatives'])==2

def test_low_confidence_stops_before_regeneration(engine,tmp_path):
    c,r=begin(engine); j=advance_to_decision(engine,tmp_path)
    complete(engine,j,decision(j,confidence=.1))
    assert engine.snapshot(r['id'])['run']['state']=='READY_FOR_REVIEW'
    assert len(engine.snapshot(r['id'])['creatives'])==2

def test_budget_enforced_before_next_model_call(engine):
    c,r=begin(engine,max_model_calls=1); j=engine.claim('test-worker'); complete(engine,j,plan_for(j))
    assert engine.claim('test-worker') is None
    assert engine.snapshot(r['id'])['run']['stop_reason']=='MODEL_CALL_BUDGET_EXHAUSTED'

def test_dollar_ceiling_and_missing_price_fail_closed(engine):
    c,r=begin(engine,max_cost_usd=.015,generation_cost_reservation_usd=.01)
    j=engine.claim('test-worker'); complete(engine,j,plan_for(j))
    assert engine.claim('test-worker') is None
    assert engine.snapshot(r['id'])['run']['stop_reason']=='COST_BUDGET_EXHAUSTED'

def test_evaluator_failure_does_not_deadlock(engine,tmp_path):
    c,r=begin(engine); j=engine.claim('test-worker'); complete(engine,j,plan_for(j))
    approve_pending(engine)
    for _ in range(2):
        j=engine.claim('test-worker'); complete(engine,j,generated(engine,j,tmp_path))
    for _ in range(2):
        j=engine.claim('test-worker'); engine.fail(j['id'],FailJob(worker_id='test-worker',lease_token=j['lease_token'],code='FAILED',detail='fixture failure',gpu_seconds=.5))
    snap=engine.snapshot(r['id']); assert snap['run']['state']=='NEEDS_ATTENTION'
    assert snap['run']['stats']['gpu_seconds']==1
    assert engine.resume(r['id'])['state'] == 'EVALUATING'
    assert engine.claim('test-worker') is not None

def test_mixed_checkpoint_comparison_rejected(engine,tmp_path):
    c,r=begin(engine); j=engine.claim('test-worker'); complete(engine,j,plan_for(j))
    approve_pending(engine)
    for _ in range(2):
        j=engine.claim('test-worker'); complete(engine,j,generated(engine,j,tmp_path))
    for i in range(2):
        j=engine.claim('test-worker'); complete(engine,j,evaluated(j,version=f'version-{i}'))
    assert engine.snapshot(r['id'])['run']['stop_reason']=='INCOMPATIBLE_VISION_EVALUATOR_CONFIGURATIONS'

def test_human_feedback_persists(engine,tmp_path):
    c,r=begin(engine); j=advance_to_decision(engine,tmp_path); identity=j['payload']['allowed_creative_ids'][0]
    engine.feedback(c['id'],FeedbackRequest(creative_id=identity,kind='like'))
    assert engine.campaign_detail(c['id'])['feedback'][0]['kind']=='like'

@pytest.mark.parametrize('params',[{'width':100000},{'num_inference_steps':10000},{'strength':float('nan')},{'num_inference_steps':2.5}])
def test_reasoner_cannot_escalate_compute(params):
    with pytest.raises(ValidationError): CandidatePlan(prompt='test',strategy='test',edit_intent=EditIntent(primary_goal='test'),parameters=params)

def test_claims_need_literal_provenance(engine):
    with pytest.raises(DomainError): engine.create_campaign(CampaignSpec(title='test',brief='Product is blue',brand=BrandSpec(name='test',approved_claims=[Claim(text='cures disease',source_id='brief',source_quote='cures disease')])))

def test_missing_proxy_is_not_zero_score():
    with pytest.raises(ValidationError): EvaluationResult(evaluator='tsam',status='UNAVAILABLE',provenance=P,scores={'emotion':Score(value=.8,source='fake',meaning='fake')},limitations=['proxy'])
    with pytest.raises(ValidationError): EvaluationResult(evaluator='tribe',status='SUCCEEDED',provenance=P,scores={'ctr':Score(value=.8,source='fake',meaning='fake')},limitations=['proxy'])

@pytest.mark.parametrize('probabilities,confidence',[({'a':.4,'b':.4},.8),({'a':float('nan'),'b':0},.8),({'a':.2,'b':.8},.8),({'a':1,'b':0},2)])
def test_typesafe_rejects_malformed_distributions(probabilities,confidence):
    with pytest.raises(ProviderFailure): TypeSafeKernel.validate_choice({'type':'choice','choice':'a','probabilities':probabilities,'confidence':confidence},{'a':None,'b':None})

def test_actual_typesafe_http_contract_with_test_transport(settings):
    s=settings.model_copy(update={'typesafe_api_key':__import__('pydantic').SecretStr('test-key')})
    def handler(request):
        assert str(request.url)=='https://api.typesafe.ai/v1/systemone'
        body=json.loads(request.content); assert body['model']=='jev-latest'
        answers={}
        for name, question in body['questions'].items():
            assert question['type']=='choice'
            selected={'next_action':'REGENERATE','best_candidate':'one','next_strategy':'STRONGER_HOOK'}[name]
            answers[name]={'type':'choice','choice':selected,'confidence':.9,'probabilities':{k:1.0 if k==selected else 0.0 for k in question['criteria']}}
        return httpx.Response(200,json={'model':'jev-latest','answers':answers,'usage':{'input_tokens':10,'output_tokens':10}})
    result=TypeSafeKernel(s,httpx.Client(transport=httpx.MockTransport(handler))).decide({'allowed_actions':['REGENERATE','ASK_HUMAN'],'allowed_creative_ids':['one','two'],'config':{'beam_width':2}})
    assert result.decision=='REGENERATE'; assert result.selected_creative_ids==['one','two']

def test_api_auth_separates_workers_and_human(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/v2/capabilities').status_code==401
        assert c.get('/api/v2/capabilities',headers={'Authorization':'Bearer '+'w'*40}).status_code==403
        assert c.post('/auth/local',headers={'Origin':settings.frontend_origin}).status_code==403
        login=c.post('/auth/local',headers={'X-NeuroLoop-Bootstrap':'b'*40}); assert login.status_code==200
        token=login.json()['token']; h={'Authorization':'Bearer '+token}
        assert c.get('/api/v2/capabilities',headers=h).status_code==200
        assert c.post('/auth/revoke',headers=h).status_code==200
        assert c.get('/api/v2/capabilities',headers=h).status_code==401

def test_cross_origin_write_denied(settings):
    with TestClient(create_app(settings)) as c:
        assert c.post('/auth/login',json={'token':'o'*40},headers={'Origin':'https://evil.invalid'}).status_code==403

def test_path_traversal_rejected(settings):
    with pytest.raises(StorageError): ObjectStore(settings).local_path('../../secret')

def test_molab_permission_is_explicit(engine):
    with pytest.raises(DomainError): engine.register_worker(WorkerHello(worker_id='molab',provider='molab',capabilities={}))


def test_decision_uses_online_generator_contract_after_split_vision_worker(engine, tmp_path):
    from neuroloop_app.db import Worker
    _, run = begin(engine)
    engine.register_worker(WorkerHello(worker_id='vision-only', capabilities={'evaluate_vision': {'status': 'READY'}}))
    with engine.store.transaction() as session:
        generator = session.get(Worker, 'test-worker')
        generator.capabilities = {k: v for k, v in generator.capabilities.items() if k != 'evaluate_vision'}
        generator.capabilities = {**generator.capabilities, 'generate_image': {'status': 'READY', 'supports_regeneration': False}}
    for _ in range(4):
        job = engine.claim('test-worker')
        if job['kind'] == 'PLAN': complete(engine, job, plan_for(job))
        elif job['kind'] == 'REVIEW_PLAN': complete(engine, job, review_for(job['payload']))
        else: complete(engine, job, generated(engine, job, tmp_path))
    for _ in range(2):
        job = engine.claim('vision-only')
        engine.complete(job['id'], CompleteJob(worker_id='vision-only', lease_token=job['lease_token'], result=evaluated(job)))
    decision_job = engine.claim('test-worker')
    assert decision_job['kind'] == 'DECIDE'
    assert decision_job['payload']['generator_contract']['supports_regeneration'] is False
    assert 'REGENERATE' not in decision_job['payload']['allowed_actions']


def test_stopped_plan_still_gets_an_explanation_without_fabricated_media(engine):
    _, run = begin(engine)
    engine.register_worker(WorkerHello(worker_id='summary-worker', capabilities={'summary': {'status': 'READY', 'model': 'TEST_ONLY'}}))
    job = engine.claim('test-worker')
    complete(engine, job, plan_for(job))
    job = engine.claim('test-worker')
    complete(engine, job, review_for(job['payload'], 'REJECT'))
    summary = engine.claim('summary-worker')
    assert summary['kind'] == 'SUMMARY'
    assert summary['payload']['asset_ids'] == []
    assert summary['payload']['evidence'] == []
    assert {j['kind'] for j in summary['payload']['execution']['planning_receipts']} == {'PLAN', 'REVIEW_PLAN'}
    snapshot = engine.snapshot(run['id'])
    assert snapshot['run']['stop_reason'] == 'TYPESAFE_PLAN_REJECTED'
    assert not snapshot['creatives']


def test_automatic_summary_preserves_decision_and_validates_citations(engine, tmp_path):
    from neuroloop_app.db import NotebookEvidence
    _, run = begin(engine)
    engine.register_worker(WorkerHello(worker_id='summary-worker', capabilities={'summary': {'status': 'READY', 'model': 'TEST_ONLY'}}))
    chosen = advance_to_decision(engine, tmp_path)
    complete(engine, chosen, decision(chosen, action='KEEP'))
    summary_job = engine.claim('summary-worker')
    assert summary_job['kind'] == 'SUMMARY'
    engine.fail(summary_job['id'], FailJob(worker_id='summary-worker', lease_token=summary_job['lease_token'],
                                         code='INVALID_OUTPUT', detail='Test fixture: invalid citation'))
    assert engine.snapshot(run['id'])['run']['stop_reason'] == 'KEEP'
    engine.retry_summary(run['id'])
    engine.retry_summary(run['id'])  # One delivery job, even after repeated clicks.
    summary_job = engine.claim('summary-worker')
    assert summary_job['attempt'] == 2
    payload = summary_job['payload']
    result = {'summary': 'Test fixture summary', 'findings': [], 'limitations': [], 'next_steps': [],
              'evidence_ids': ['invented'], 'provider_receipt': {'model': 'TEST_ONLY'},
              'input_digest': digest({'evidence': payload['evidence'], 'execution': payload['execution']})}
    with pytest.raises(DomainError, match='unknown evidence'):
        engine.complete(summary_job['id'], CompleteJob(worker_id='summary-worker', lease_token=summary_job['lease_token'], result=result))
    result['evidence_ids'] = [e['id'] for e in payload['evidence']]
    request = CompleteJob(worker_id='summary-worker', lease_token=summary_job['lease_token'], result=result)
    engine.complete(summary_job['id'], request)
    engine.complete(summary_job['id'], request)
    with engine.store.read() as session:
        assert len(list(session.scalars(select(NotebookEvidence)))) == 2
    snap = engine.snapshot(run['id'])
    assert snap['run']['state'] == 'READY_FOR_REVIEW' and snap['run']['stop_reason'] == 'KEEP'
    assert next(j for j in snap['jobs'] if j['kind'] == 'SUMMARY')['error'] is None
    assert engine.claim('summary-worker') is None
