from neuroloop.db import Session,Project,Run,ArchivedRecord
from neuroloop import services
from neuroloop.research import ledger
from neuroloop.schemas import ProjectCreate

def test_retirement_preserves_research_but_removes_active_workspace(client):
    project=services.create_project(ProjectCreate(name='Archived research fixture'))
    with Session.begin() as db:
        run=Run(project_id=project['id'],status='completed',stage='Recorded',compute_seconds=2)
        db.add(run);db.flush();identity=run.id
        db.add(ArchivedRecord(key='project:'+project['id'],kind='project',record_id=project['id']))
        db.add(ArchivedRecord(key='run:'+identity,kind='run',record_id=identity))
    visible=services.dashboard()
    assert all(p['id']!=project['id'] for p in visible['projects'])
    assert all(r['id']!=identity for r in visible['runs'])
    saved=next(r for r in ledger()['runs'] if r['id']==identity)
    assert saved['archived'] is True and saved['compute_seconds']==2
    with Session() as db:assert db.get(Project,project['id']) is not None

def test_research_endpoint_requires_auth_and_returns_real_ledger(client,headers):
    assert client.get('/api/research').status_code==401
    response=client.get('/api/research',headers=headers)
    assert response.status_code==200
    assert 'totals' in response.json()
    assert all('prediction_path' not in row for row in response.json()['evaluations'])

def test_service_checks_do_not_claim_missing_sponsors_are_connected(monkeypatch):
    from neuroloop import integrations
    monkeypatch.delenv('WANDB_API_KEY',raising=False)
    class Response:status_code=200
    monkeypatch.setattr(integrations.httpx,'get',lambda *args,**kwargs:Response())
    values={x['name']:x for x in integrations.check_connections()['connections']}
    assert values['marimo']['status']=='connected'
    assert values['Weights & Biases Weave']['status']=='not_configured'
    assert values['CoreWeave']['status']=='not_used_local_compute'
    assert values['ARIA / W&B Launch']['status']=='not_configured'
