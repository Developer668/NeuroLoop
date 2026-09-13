"""Adversarial contract tests; model fixtures are confined to tests."""
import copy
import pytest
import httpx
from pydantic import SecretStr
from neuroloop_app.sponsors import WandBReasoner, ProviderFailure
from test_loop import (engine, settings, begin, complete, plan_for, review_for,
                       advance_to_decision, decision)
from neuroloop_app.engine import DomainError


def test_reasoning_exhaustion_reports_token_budget_without_creating_plan(settings):
    settings.wandb_api_key = SecretStr('test-only')
    settings.inference_model = 'zai-org/GLM-5.3-Flash'
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        'model': settings.inference_model,
        'choices': [{'finish_reason': 'length', 'message': {'content': None}}],
        'usage': {'completion_tokens': 8192},
    })))
    with pytest.raises(ProviderFailure, match='output token budget') as failure:
        WandBReasoner(settings, client).plan({})
    assert failure.value.code == 'INVALID_OUTPUT'
    assert not failure.value.safe_to_retry


def test_no_generation_before_typesafe_approves(engine):
    _, run = begin(engine)
    job = engine.claim('test-worker')
    complete(engine, job, plan_for(job))
    snapshot = engine.snapshot(run['id'])
    assert not snapshot['creatives']
    assert not any(j['kind'] == 'GENERATE' for j in snapshot['jobs'])
    review = engine.claim('test-worker')
    assert review['kind'] == 'REVIEW_PLAN'
    complete(engine, review, review_for(review['payload'], 'REJECT'))
    snapshot = engine.snapshot(run['id'])
    assert snapshot['run']['stop_reason'] == 'TYPESAFE_PLAN_REJECTED'
    assert not snapshot['creatives']
    assert snapshot['run']['stats']['model_calls'] == 2


def test_approved_but_uncertain_plan_is_not_reported_as_rejected(engine):
    _, run = begin(engine)
    job = engine.claim('test-worker')
    complete(engine, job, plan_for(job))
    review = engine.claim('test-worker')
    answer = review_for(review['payload'])
    answer['confidence'] = .47
    answer['raw_response']['answers']['plan_gate']['confidence'] = .47
    complete(engine, review, answer)
    snapshot = engine.snapshot(run['id'])
    assert snapshot['run']['stop_reason'] == 'TYPESAFE_PLAN_LOW_CONFIDENCE'
    assert not snapshot['creatives']
    assert not any(j['kind'] == 'GENERATE' for j in snapshot['jobs'])


def test_review_must_bind_exact_plan_and_provider_answer(engine):
    _, run = begin(engine)
    job = engine.claim('test-worker')
    complete(engine, job, plan_for(job))
    review = engine.claim('test-worker')
    answer = review_for(review['payload'])
    altered = copy.deepcopy(answer)
    altered['plan_hash'] = '0' * 64
    with pytest.raises(DomainError):
        complete(engine, review, altered)
    altered = copy.deepcopy(answer)
    altered['raw_response']['answers']['plan_gate']['choice'] = 'REJECT'
    with pytest.raises(DomainError):
        complete(engine, review, altered)
    assert not engine.snapshot(run['id'])['creatives']
    complete(engine, review, answer)
    assert len(engine.snapshot(run['id'])['creatives']) == 2


@pytest.mark.parametrize('corruption', ['missing', 'value', 'time', 'foreign'])
def test_child_cannot_invent_response_evidence(engine, tmp_path, corruption):
    begin(engine)
    job = advance_to_decision(engine, tmp_path)
    complete(engine, job, decision(job))
    job = engine.claim('test-worker')
    plan = plan_for(job)
    intent = plan['candidates'][0]['edit_intent']
    if corruption == 'missing':
        intent['optimization'] = None
    elif corruption == 'value':
        intent['optimization']['observation']['value'] = .999
    elif corruption == 'time':
        intent['optimization']['observation']['time_range'] = [3.1, 4.4]
    else:
        intent['optimization']['creative_evidence']['evaluation_id'] = 'foreign'
    with pytest.raises(DomainError):
        complete(engine, job, plan)


def test_harness_reverts_worse_candidate(engine, tmp_path):
    _, run = begin(engine, max_rounds=3)
    job = advance_to_decision(engine, tmp_path)
    first = decision(job)
    incumbent = first['selected_creative_ids'][0]
    complete(engine, job, first)
    job = advance_to_decision(engine, tmp_path)
    # Exercise the guard against a provider selecting a worse comparable score.
    from neuroloop_app.db import Job
    with engine.store.transaction() as session:
        row = session.get(Job, job['id'])
        payload = copy.deepcopy(row.payload)
        child = next(b for b in payload['evidence_bundles'] if b['creative_id'] != incumbent)
        child['quality']['value'] = .01
        row.payload = payload
        child_id = child['creative_id']
    proposed = decision(job, action='KEEP')
    proposed['selected_creative_ids'] = [child_id]
    complete(engine, job, proposed)
    snapshot = engine.snapshot(run['id'])
    assert snapshot['run']['champion_id'] == incumbent
    assert snapshot['run']['stop_reason'] == 'REVERTED_LOWER_PROXY_QUALITY'
