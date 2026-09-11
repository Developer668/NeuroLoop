import json,uuid
from types import SimpleNamespace
import pytest
from sqlalchemy import text
from neuroloop.db import engine,initialize
from neuroloop.config import settings

def test_local_session_is_revoked(client):
    token=client.post('/auth/local',headers={'origin':'http://localhost:3010','x-neuroloop-local':'browser'}).json()['token']
    headers={'Authorization':'Bearer '+token}
    assert client.get('/api/dashboard',headers=headers).status_code==200
    assert client.post('/auth/revoke',headers=headers).json()['revoked']
    assert client.get('/api/dashboard',headers=headers).status_code==401

def test_neuro_is_explicit_and_authenticated(client,headers):
    assert client.post('/api/neuro/command',json={'command':'/latest'}).status_code==401
    result=client.post('/api/neuro/command',headers=headers,json={'command':'tell me feelings'}).json()
    assert result['provider']=='local-deterministic-commands'
    assert 'not connected' in result['message']
    assert client.post('/api/neuro/command',headers=headers,json={'command':'/status','code':'bad'}).status_code==422

def test_migrations_are_idempotent(client):
    initialize();initialize()
    with engine.connect() as db:
        versions=[r[0] for r in db.execute(text('SELECT version FROM schema_version ORDER BY version'))]
    assert versions==[1,2,3]

def test_future_schema_rejected(client):
    with engine.begin() as db:db.execute(text("INSERT INTO schema_version(version,installed_at) VALUES (999,'future')"))
    try:
        with pytest.raises(RuntimeError,match='newer'):initialize()
    finally:
        with engine.begin() as db:db.execute(text('DELETE FROM schema_version WHERE version=999'))

def test_receipt_requires_remote_readback_and_redacts_payload(client,monkeypatch):
    from neuroloop.delivery import enqueue,drain,receipts
    monkeypatch.setattr(settings(),'weave_enabled',True)
    monkeypatch.setenv('WANDB_PROJECT','entity/project')
    identity=str(uuid.uuid4())
    enqueue('test.actual-outbox',{'run_id':'local','secret':'never export','gain':.1},identity)
    enqueue('test.actual-outbox',{'run_id':'local'},identity)
    class Transport:
        def create_call(self,**kwargs):
            assert 'secret' not in kwargs['inputs']
            self.id=kwargs['_call_id_override'];return SimpleNamespace(id=self.id)
        def finish_call(self,*args,**kwargs):pass
        def flush(self):pass
        def get_call(self,identity):raise ConnectionError('secret-bearing request text')
    transport=Transport()
    assert drain(connection=transport)==0
    row=next(r for r in receipts() if r['id']==identity)
    assert row['status']=='retry' and row['url'] is None and row['error']=='ConnectionError'
    with engine.begin() as db:db.execute(text('UPDATE external_receipts SET next_attempt=0 WHERE id=:id'),{'id':identity})
    transport.get_call=lambda identity:SimpleNamespace(id=identity,ended_at='done')
    assert drain(connection=transport)==1
    row=next(r for r in receipts() if r['id']==identity)
    assert row['attempts']==2 and row['status']=='delivered' and identity in row['url']

def test_proposal_rejects_executable_fields(client,headers):
    response=client.post('/api/agent/proposals',headers=headers,json={'version':1,'source':'ARIA','base_run_id':'missing','operator':'contrast_up','hypothesis':'Check a contrast change','command':'python dangerous.py'})
    assert response.status_code==422

def test_proposal_missing_context_cannot_queue(client,headers):
    response=client.post('/api/agent/proposals',headers=headers,json={'version':1,'source':'ARIA','base_run_id':'missing','operator':'contrast_up','hypothesis':'Check a contrast change'})
    assert response.status_code==400
