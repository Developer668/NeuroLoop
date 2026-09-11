import pytest

from neuroloop.schemas import RunCreate
from neuroloop.response import ensemble, target_score
from neuroloop.generation import DeferredProvider, statuses
from neuroloop import kragel


def test_response_target_requires_target_and_a_response_source():
    with pytest.raises(ValueError, match='requires a target'):
        RunCreate(project_id='p', objective='response_target')
    with pytest.raises(ValueError, match='requires TSAM, Kragel'):
        RunCreate(project_id='p', objective='response_target', target={'emotions': {'happiness': {'desired': .8}}})
    item=RunCreate(project_id='p', objective='response_target', target={'emotions': {'happiness': {'desired': .8}}}, include_kragel=True)
    assert item.target.emotions['happiness'].desired == .8


def test_response_ensemble_preserves_sources_and_disagreement():
    evidence={
        'tsam': {'status':'experimental','labels':['Anger','Contempt','Disgust','Fear','Happiness','Neutral','Sadness','Surprise'],
                 'windows':[{'logits':[-2,-3,-3,-2,4,-2,-2,2]}]},
        'kragel': {'status':'experimental','aggregate':{'amused':.08,'angry':-.04,'content':.05,'fearful':-.03,'neutral':-.06,'sad':-.02,'surprised':.04}},
    }
    report=ensemble(evidence)
    assert report['active_sources']==['tsam','kragel']
    assert report['sources']['tsam']['happiness'] > report['sources']['tsam']['fear']
    assert report['values']['happiness'] is not None
    assert report['mean_disagreement'] is not None
    assert 0 <= report['mean_disagreement'] <= 1


def test_response_target_score_moves_toward_declared_emotion():
    base={'values':{'happiness':.25,'fear':.50},'mean_disagreement':.1}
    improved={'values':{'happiness':.78,'fear':.08},'mean_disagreement':.1}
    target={'emotions':{'happiness':{'desired':.8,'weight':1},'fear':{'desired':.05,'weight':1}}}
    assert target_score(improved,target)['value'] > target_score(base,target)['value']


def test_generation_sponsors_are_explicitly_deferred():
    values=statuses()
    assert {x['name'] for x in values}=={'Ideogram 4','MiniMax H3'}
    assert all(x['status']=='awaiting_sponsor_access' for x in values)
    provider=DeferredProvider('Test','No credits',('generate',))
    with pytest.raises(RuntimeError, match='not configured'):
        provider.generate({})


def test_kragel_status_fails_closed_without_assets(monkeypatch,tmp_path):
    monkeypatch.setattr(kragel,'_source',lambda:tmp_path/'missing')
    monkeypatch.setattr(kragel,'_geometry',lambda name:tmp_path/name)
    value=kragel.status()
    assert value['status']=='missing_assets'
    assert value['missing']


def test_response_target_run_does_not_require_reference(client,headers):
    from backend.tests.test_contracts import upload, project
    asset=upload(client,headers)
    p=project(client,headers,asset)
    body={'project_id':p['id'],'mode':'optimize','objective':'response_target',
          'target':{'emotions':{'happiness':{'desired':.8}}},'include_kragel':True,
          'allow_static_presentation':True,'max_evaluations':2}
    response=client.post('/api/runs',headers=headers,json=body)
    assert response.status_code==202,response.text
    assert response.json()['config']['objective']=='response-target-distance/v1'


def test_reference_objective_still_requires_reference(client,headers):
    from backend.tests.test_contracts import upload, project
    asset=upload(client,headers)
    p=project(client,headers,asset)
    response=client.post('/api/runs',headers=headers,json={'project_id':p['id'],'mode':'optimize','allow_static_presentation':True})
    assert response.status_code==400
    assert 'reference' in response.json()['detail'].lower()

def test_worker_cache_contract_includes_response_sources():
    import inspect
    from neuroloop import worker
    source=inspect.getsource(worker.evaluation)
    assert "'include_tsam'" in source
    assert "'include_kragel'" in source

def test_response_target_worker_keeps_improving_candidate(client,headers,monkeypatch):
    """Exercise the real controller/ledger with deterministic evaluator outputs, no GPU/network."""
    from backend.tests.test_contracts import upload, project
    from neuroloop import worker
    from neuroloop.db import Evaluation, Session, Experiment, Run

    asset=upload(client,headers,name='loop.png')
    p=project(client,headers,asset)
    request={
        'project_id':p['id'],'mode':'optimize','objective':'response_target',
        'target':{'goal':'positive response','emotions':{'happiness':{'desired':.8,'weight':1}}},
        'include_kragel':True,'allow_static_presentation':True,
        'operators':['brightness_up'],'max_evaluations':2,'target_score':.95,
    }
    queued=client.post('/api/runs',headers=headers,json=request)
    assert queued.status_code==202,queued.text
    run_id=queued.json()['id']
    original=worker.get_asset(asset['id'])
    calls={'n':0}

    def fake_evaluation(identity, selected, config):
        calls['n']+=1
        happiness=.2 if calls['n']==1 else .8
        return Evaluation(
            id='baseline-eval' if calls['n']==1 else 'candidate-eval',
            asset_id=selected.id,cache_key='x'+str(calls['n']),evaluator='fixture',profile='fixed-profile',
            evidence={'response_ensemble':{
                'profile':'fixture','values':{'happiness':happiness},'sources':{},'source_weights':{},
                'active_sources':['fixture'],'disagreement':{},'mean_disagreement':None,
                'confidence':'fixture','interpretation':'deterministic controller fixture',
            }},prediction_path=None,duration_seconds=0,
        )

    monkeypatch.setattr(worker,'evaluation',fake_evaluation)
    monkeypatch.setattr(worker,'render_candidate',lambda *args,**kwargs: original)
    monkeypatch.setattr(worker,'planner_proposal',lambda *args,**kwargs: None)
    monkeypatch.setattr(worker,'record_evidence',lambda *args,**kwargs: None)

    with pytest.raises(worker.StopRun,match='response target reached'):
        worker.execute_run(run_id)

    with Session() as db:
        row=db.get(Run,run_id)
        experiments=db.query(Experiment).filter(Experiment.run_id==run_id).all()
        assert row.result['metric']=='response-target-distance/v1'
        assert row.result['best_metric']['value'] > row.result['baseline_metric']['value']
        assert len(experiments)==1
        assert experiments[0].decision=='kept'
        assert experiments[0].evidence['response_ensemble']['values']['happiness']==.8
