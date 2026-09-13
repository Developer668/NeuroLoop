"""Service contract and recovery tests; all external responses are test doubles."""
from pathlib import Path
import json
import httpx
import pytest
from sqlalchemy import create_engine, inspect, select
from fastapi.testclient import TestClient
from alembic.config import Config
from alembic import command
from neuroloop_app.config import Settings
from neuroloop_app.db import Store, Deployment, Asset, Run, Trace, Base
from neuroloop_app.domain import uid, digest, now
from neuroloop_app.engine import LoopEngine
from neuroloop_app.storage import ObjectStore
from neuroloop_app.meta import MetaClient, MetaService, MetaFailure
from neuroloop_app.telemetry import WeaveExporter
from neuroloop_app.api import create_app
from test_loop import campaign, begin

@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None,data_dir=tmp_path,operator_token='o'*40,agent_token='a'*40,worker_token='w'*40,signing_key='s'*40,local_bootstrap_token='b'*40,
                    META_ACCESS_TOKEN='test-not-real',meta_graph_version='v99.0')

@pytest.fixture
def engine(settings):
    s=Store(settings);s.initialize();return LoopEngine(s,ObjectStore(settings))


def test_research_bundle_requires_worker_and_supports_resume(settings, tmp_path):
    bundle = tmp_path / 'runtime.zip'
    bundle.write_bytes(b'0123456789')
    settings.research_bundle_path = bundle
    with TestClient(create_app(settings)) as client:
        url = '/api/v2/workers/research-bundle'
        assert client.get(url).status_code == 401
        assert client.get(url, headers={'Authorization': 'Bearer ' + 'a'*40}).status_code == 403
        response = client.get(url, headers={'Authorization': 'Bearer ' + 'w'*40, 'Range': 'bytes=5-'})
        assert response.status_code == 206
        assert response.content == b'56789'
        settings.research_bundle_path = None
        assert client.get(url, headers={'Authorization': 'Bearer ' + 'w'*40}).status_code == 404


def approved(engine,tmp_path):
    from PIL import Image
    c,r=begin(engine);p=tmp_path/'TEST_ONLY.png';Image.new('RGB',(64,64)).save(p)
    a=engine.add_asset(c['id'],p,'TEST_ONLY.png')
    spec={'ad_account_id':'123','page_id':'456','currency':'USD','daily_budget_minor':100,'audience':{'geo_locations':{'countries':['US']}},
          'message':'Test fixture','headline':'Test fixture','destination':'https://example.test/', 'status':'PAUSED','asset_sha256':a['sha256'],'asset_id':a['id'],
          'research_license_approved_for_commercial_use':True,'special_ad_categories':[],'creative_id':'test-only'}
    with engine.store.transaction() as s:
        d=Deployment(id=uid(),run_id=r['id'],spec=spec,review_digest=digest(spec),state='APPROVED',approved_at=now(),approved_by='human',entities={},metrics=[])
        s.add(d);s.flush();return d.id,d.review_digest


def graph_handler(request):
    from urllib.parse import parse_qs
    if request.method=='GET':
        if request.url.path.endswith('act_123'):return httpx.Response(200,json={'id':'act_123','currency':'USD'})
        if request.url.path.endswith('/insights'):return httpx.Response(200,json={'data':[]})
        return httpx.Response(200,json={'id':request.url.path.rsplit('/',1)[-1],'status':'PAUSED'})
    edge=request.url.path.rsplit('/',1)[-1]
    form=parse_qs(request.content.decode())
    if edge in {'campaigns','adsets','ads'}:assert form['status']==['PAUSED']
    if edge=='adimages':return httpx.Response(200,json={'images':{'fixture':{'hash':'TEST_ONLY_HASH'}}})
    return httpx.Response(200,json={'id':{'campaigns':'11','adsets':'12','adcreatives':'13','ads':'14'}[edge]})


def test_meta_paused_pipeline_readback_and_insights(engine,tmp_path,settings):
    ident,review=approved(engine,tmp_path);seen=[]
    def handler(req):seen.append(str(req.url));return graph_handler(req)
    service=MetaService(engine.store,engine.objects,MetaClient(settings,httpx.Client(transport=httpx.MockTransport(handler))))
    service.enqueue(ident,review);result=service.drain();assert result['status']=='DEPLOYED'
    before=len(seen);service.enqueue(ident,review);assert service.drain()['status']=='IDLE';assert len(seen)==before
    receipt=service.insights(ident,'2026-09-01','2026-09-12');assert receipt['rows']==[];assert receipt['conclusion']=='INCONCLUSIVE'
    with engine.store.read() as s:
        d=s.get(Deployment,ident);assert d.entities['ad_id']=='14';assert len(d.metrics)==1


def test_meta_ambiguous_post_never_reissues(engine,tmp_path,settings):
    ident,review=approved(engine,tmp_path);posts=[]
    def handler(req):
        if req.method=='POST':posts.append(req);raise httpx.ReadTimeout('test',request=req)
        return graph_handler(req)
    service=MetaService(engine.store,engine.objects,MetaClient(settings,httpx.Client(transport=httpx.MockTransport(handler))))
    service.enqueue(ident,review);assert service.drain()['status']=='NEEDS_RECONCILIATION'
    assert service.drain()['status']=='IDLE';assert len(posts)==1
    from neuroloop_app.engine import DomainError
    with pytest.raises(DomainError):service.enqueue(ident,review)


def test_meta_mismatched_currency_creates_nothing(engine,tmp_path,settings):
    ident,review=approved(engine,tmp_path)
    def handler(req):assert req.method=='GET';return httpx.Response(200,json={'id':'act_123','currency':'EUR'})
    service=MetaService(engine.store,engine.objects,MetaClient(settings,httpx.Client(transport=httpx.MockTransport(handler))))
    service.enqueue(ident,review);assert service.drain()['status']=='FAILED'


@pytest.mark.parametrize('edge',['campaigns','adsets','ads'])
def test_meta_active_status_impossible(settings,edge):
    with pytest.raises(MetaFailure):MetaClient(settings).create('act_123',edge,{'status':'ACTIVE'})


def test_agent_cannot_become_human(settings):
    with TestClient(create_app(settings)) as c:
        assert c.post('/auth/login',json={'token':'a'*40}).status_code==401
        assert c.post('/auth/local',headers={'Authorization':'Bearer '+'a'*40}).status_code==403
        assert c.get('/api/v2/campaigns',headers={'Authorization':'Bearer '+'a'*40}).status_code==200
        assert c.post('/api/v2/experiments/'+uid()+'/approve',headers={'Authorization':'Bearer '+'a'*40},json={'review_digest':'0'*64,'confirmation':'APPROVE PAUSED DEPLOYMENT'}).status_code==403


def test_weave_preserves_real_hierarchy_and_readback(engine,settings):
    settings.weave_enabled=True;settings.wandb_project='test/project';settings.wandb_api_key='test-key'
    # Pydantic assignment validation is intentionally not used for settings in tests.
    from pydantic import SecretStr
    settings.wandb_api_key=SecretStr('test-key')
    c,r=begin(engine);remote={}
    def handler(req):
        body=json.loads(req.content)
        if req.url.path=='/call/read':return httpx.Response(200,json={'call':remote.get(body['id'])})
        if req.url.path=='/call/start':remote[body['start']['id']]=body['start'];return httpx.Response(200,json={'id':body['start']['id']})
        if req.url.path=='/call/end':remote[body['end']['id']].update(body['end']);return httpx.Response(200,json={})
        raise AssertionError(str(req.url))
    exporter=WeaveExporter(engine.store,httpx.Client(transport=httpx.MockTransport(handler)))
    assert exporter.drain(20)['delivered']>=1
    assert remote[r['id']]['trace_id']==r['id']
    with engine.store.read() as s:
        rows=list(s.scalars(select(Trace)))
        assert all(t.url for t in rows if t.delivered_revision)


def test_static_migrations_match_models(tmp_path):
    root=Path(__file__).resolve().parents[1]
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
    url='sqlite:///'+str(tmp_path/'migration.sqlite3');cfg.attributes['database_url']=url
    command.upgrade(cfg,'head')
    db=create_engine(url)
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    with db.connect() as c:assert compare_metadata(MigrationContext.configure(c),Base.metadata)==[]
    command.downgrade(cfg,'base')
    assert inspect(db).get_table_names()==['alembic_version']
