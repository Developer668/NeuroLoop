from types import SimpleNamespace
import pytest
from sqlalchemy import select
from neuroloop_app.outcome_telemetry import percentile, snapshot, trace_summary
from neuroloop_app.config import Settings
from neuroloop_app.db import Store, Trace, Job
from neuroloop_app.engine import LoopEngine
from neuroloop_app.storage import ObjectStore
from test_loop import begin


def test_registered_capabilities_do_not_verify_execution(tmp_path):
    store = Store(Settings(_env_file=None, data_dir=tmp_path)); store.initialize()
    begin(LoopEngine(store, ObjectStore(store.settings)))
    data = snapshot(store)
    assert data['metrics']['verification_runs_attempted'] == 0
    assert data['metrics']['full_loop_verified_rate'] is None
    assert not data['readiness'][0]['control_plane_verified']
    assert data['metrics']['eligible_candidate_rate'] is None
    assert data['capabilities']
    assert all(c['execution_status'] == 'NO_CAMPAIGN_EXECUTION' for c in data['capabilities'])
    assert data['events']
    assert all('brief' not in e and 'prompt' not in e and 'reason' not in e for e in data['events'])


def test_readiness_requires_evidence_and_actual_revision_child(tmp_path):
    from test_loop import advance_to_decision, complete, decision
    store = Store(Settings(_env_file=None, data_dir=tmp_path)); store.initialize()
    engine = LoopEngine(store, ObjectStore(store.settings))
    begin(engine, max_rounds=2)
    first = advance_to_decision(engine, tmp_path)
    data = snapshot(store)
    assert data['metrics']['eligible_candidate_rate'] == 1
    assert not data['readiness'][0]['decision_verified']
    complete(engine, first, decision(first))
    assert not snapshot(store)['readiness'][0]['full_loop_verified']
    advance_to_decision(engine, tmp_path)
    data = snapshot(store)
    assert data['readiness'][0]['child_generation_verified']
    assert data['metrics']['full_loop_verified_rate'] == 1
    assert data['decision_gates'][-1]['applied_action'] == 'REGENERATE'


def test_readiness_uses_engine_hard_constraints(tmp_path):
    from test_loop import advance_to_decision
    from neuroloop_app.db import Evaluation, Creative
    store = Store(Settings(_env_file=None, data_dir=tmp_path)); store.initialize()
    engine = LoopEngine(store, ObjectStore(store.settings))
    begin(engine); advance_to_decision(engine, tmp_path)
    with store.transaction() as session:
        for evaluation in session.scalars(select(Evaluation)):
            evaluation.result = {**evaluation.result, 'constraints': []}
        for creative in session.scalars(select(Creative)):
            creative.status = 'INVALID'
    data = snapshot(store)
    assert data['metrics']['required_evidence_completion_rate'] == 1
    assert data['metrics']['eligible_candidate_rate'] == 0
    assert data['readiness'][0]['generation_verified']
    assert data['readiness'][0]['vision_verified']
    assert not data['readiness'][0]['full_loop_verified']
    assert all(c['constraints_unknown'] > 0 for c in data['candidate_evidence'])


def test_percentiles_and_missing_values():
    assert percentile([], .95) is None
    assert percentile([10, None, 30], .95) == 29
    assert percentile([float('nan'), 20], .5) == 20


def test_weave_summary_uses_real_usage_and_omits_unknown_cost():
    s = trace_summary({'output': {'model': 'actual/model', 'usage': {'prompt_tokens': 12, 'completion_tokens': 8, 'total_tokens': 20},
        'cost_usd': None, 'scores': {'creative_quality': {'value': .8, 'explanation': 'private prose'}}, 'candidate_edits': ['private prompt']}})
    assert s['usage']['actual/model']['total_tokens'] == 20
    assert s['neuroloop']['creative_quality'] == .8
    assert s['neuroloop']['cost_known'] is False
    assert 'cost_usd' not in s['neuroloop']
    assert 'private' not in str(s)


def test_snapshot_does_not_count_plan_approval_as_loop_or_human_acceptance(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    store = Store(settings); store.initialize()
    engine = LoopEngine(store, ObjectStore(settings))
    _, run = begin(engine)
    with store.transaction() as session:
        job = session.scalar(select(Job))
        job.status, job.attempt, job.result = 'SUCCEEDED', 1, {'model': 'test-only', 'cost_usd': None}
        session.add(Trace(id='11111111-1111-4111-8111-111111111111', run_id=run['id'], parent_id=run['id'],
            name='neuroloop.plan', inputs={'job_id':job.id,'attempt':1}, output={'status':'SUCCEEDED','model':'test-only','cost_usd':None}, started_at=10, ended_at=30))
    data = snapshot(store)
    assert data['metrics']['full_loop_completion_rate'] == 0
    assert data['metrics']['human_acceptance_rate'] == 0
    assert data['metrics']['median_time_to_decision_seconds'] is None
    assert data['metrics']['unknown_cost_attempts'] == 1
    assert data['metrics']['known_attempt_cost_usd'] is None
    assert data['metrics']['first_attempt_success_rate'] == 1
    assert data['metrics']['quality_gain_per_round'] is None
    assert 'brief' not in data['runs'][0]


def test_notebook_trace_does_not_swallow_model_failures(monkeypatch):
    from neuroloop_app import notebook_telemetry as nt
    calls=[]
    client=SimpleNamespace(create_call=lambda *a,**k: SimpleNamespace(summary={}),
        finish_call=lambda call,**k:calls.append(k))
    monkeypatch.setattr(nt,'_client',client)
    with pytest.raises(ValueError,match='private'):
        with nt.operation('model_inference', {'model':'isolated-unit-test'}):
            raise ValueError('private prompt must never leave the model process')
    assert calls[0]['output']['status'] == 'FAILED'
    assert str(calls[0]['exception']) == 'ValueError'
    assert 'private' not in str(calls)
