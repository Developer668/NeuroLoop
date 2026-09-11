"""Contract tests for the bounded external-agent continuation path."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import threading

import pytest
from PIL import Image

from neuroloop.db import Evaluation, Experiment, Project, Run, Session, now, uid


@pytest.fixture(autouse=True)
def allow_model_free_optional_readouts(monkeypatch):
    """Controller tests do not load optional TSAM/Kragel model assets."""
    from neuroloop import services

    monkeypatch.setattr(services, 'readout_asset_status', lambda root=None: {
        'tsam': {'ready': True, 'missing': []},
        'kragel': {'ready': True, 'missing': []},
    })


def _image_bytes(color=(90, 60, 60)):
    output = io.BytesIO()
    Image.new('RGB', (320, 180), color).save(output, format='PNG')
    return output.getvalue()


def _base_run(client, headers):
    uploaded = client.post('/api/assets', headers=headers, files={'file': ('agent.png', _image_bytes(), 'image/png')})
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    project = client.post('/api/projects', headers=headers, json={
        'name': 'External agent contract',
        'brief': 'Test a controlled evidence intervention.',
        'asset_id': asset['id'],
        'constraints': {'preserve_duration': True},
    })
    assert project.status_code == 201, project.text
    project_data = project.json()
    queued = client.post('/api/runs', headers=headers, json={
        'project_id': project_data['id'],
        'mode': 'optimize',
        'objective': 'response_target',
        'target': {'emotions': {'happiness': {'desired': .8}}},
        'include_kragel': True,
        'allow_static_presentation': True,
        'max_evaluations': 2,
    })
    assert queued.status_code == 202, queued.text
    run_id = queued.json()['id']
    with Session.begin() as db:
        run = db.get(Run, run_id)
        run.status = 'completed'
        run.finished_at = now()
        run.stop_reason = 'fixture completed without model execution'
        run.result = {
            'baseline_asset_id': asset['id'],
            'best_asset_id': asset['id'],
            'best_response': {'profile': 'fixture', 'values': {'happiness': .2}},
        }
    return project_data, run_id, asset


def test_external_agent_can_inspect_and_submit_typed_continuation(client, headers):
    project, run_id, asset = _base_run(client, headers)

    context = client.get('/api/projects/' + project['id'] + '/context', headers=headers)
    assert context.status_code == 200, context.text
    context_data = context.json()
    assert context_data['contract'] == 'project-context/v1'
    assert context_data['brief'] == project['brief']
    assert context_data['original']['id'] == asset['id']
    assert 'path' not in context_data['original']

    response = client.post('/api/agent/proposals', headers=headers, json={
        'version': 1,
        'source': 'local agent',
        'base_run_id': run_id,
        'operator': 'brightness_up',
        'hypothesis': 'A small brightness change may improve relative happiness evidence.',
    })
    assert response.status_code == 200, response.text
    proposal = response.json()
    specification = proposal['specification']
    assert proposal['status'] == 'proposed'
    assert specification['contract'] == 'agent-closed-loop/v1'
    assert specification['intervention']['version'] == 'intervention-proposal/v1'
    assert specification['intervention']['operator'] == 'brightness_up'
    assert specification['request']['operators'] == ['brightness_up']
    assert specification['agent_contract']['workflow']['max_iterations'] == 4
    assert specification['agent_contract']['workflow']['max_evaluations'] <= 12
    assert specification['agent_contract']['starting_asset_id'] == asset['id']
    assert 'command' not in specification
    assert 'url' not in specification


def test_reviewed_proposal_queues_once_and_keeps_lineage(client, headers):
    project, run_id, asset = _base_run(client, headers)
    proposal = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'brightness_up',
        'hypothesis': 'Test a bounded brightness intervention against the declared target.',
    }).json()
    first = client.post('/api/agent/proposals/' + proposal['id'] + '/execute', headers=headers, json={
        'approval_digest': proposal['approval_digest'],
    })
    assert first.status_code == 200, first.text
    continuation = first.json()
    assert continuation['status'] == 'queued'
    assert continuation['config']['agent_contract']['proposal_id'] == proposal['id']
    assert continuation['config']['agent_contract']['parent_run_id'] == run_id
    assert continuation['config']['starting_asset_id'] == asset['id']

    second = client.post('/api/agent/proposals/' + proposal['id'] + '/execute', headers=headers, json={
        'approval_digest': proposal['approval_digest'],
    })
    assert second.status_code == 200
    assert second.json()['id'] == continuation['id']
    saved = client.get('/api/agent/proposals/' + proposal['id'], headers=headers)
    assert saved.status_code == 200
    assert saved.json()['status'] == 'queued'
    assert saved.json()['run']['id'] == continuation['id']


def test_external_contract_rejects_code_paths_urls_claims_and_unknown_fields(client, headers):
    _, run_id, _ = _base_run(client, headers)
    for hypothesis in (
        'Use https://example.invalid as the next input.',
        'Run python dangerous.py before evaluating.',
        'Increase purchase probability with this edit.',
    ):
        response = client.post('/api/agent/proposals', headers=headers, json={
            'base_run_id': run_id,
            'operator': 'brightness_up',
            'hypothesis': hypothesis,
        })
        assert response.status_code == 422, response.text
    extra = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'brightness_up',
        'hypothesis': 'Test a bounded evidence intervention.',
        'command': 'rm -rf /',
    })
    assert extra.status_code == 422
    unsupported = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'execute_shell',
        'hypothesis': 'Test a bounded evidence intervention.',
    })
    assert unsupported.status_code == 422


def test_digest_and_project_snapshot_are_required_before_queueing(client, headers):
    project, run_id, _ = _base_run(client, headers)
    proposal = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'brightness_up',
        'hypothesis': 'Test a bounded evidence intervention.',
    }).json()
    wrong = client.post('/api/agent/proposals/' + proposal['id'] + '/execute', headers=headers, json={
        'approval_digest': '0' * 64,
    })
    assert wrong.status_code == 400

    with Session.begin() as db:
        db.get(Project, project['id']).brief = 'Changed after review.'
    changed = client.post('/api/agent/proposals/' + proposal['id'] + '/execute', headers=headers, json={
        'approval_digest': proposal['approval_digest'],
    })
    assert changed.status_code == 400
    assert 'changed since' in changed.json()['detail'].lower()
    saved = client.get('/api/agent/proposals/' + proposal['id'], headers=headers).json()
    assert saved['status'] == 'proposed' and saved.get('run_id') is None


def test_execution_hold_rejects_without_consuming_proposal(client, headers, monkeypatch):
    _, run_id, _ = _base_run(client, headers)
    proposal = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'brightness_up',
        'hypothesis': 'Test a bounded evidence intervention.',
    }).json()
    monkeypatch.setattr('neuroloop.execution_guard.execution_status', lambda: {'paused': True, 'reason': 'fixture hold'})
    response = client.post('/api/agent/proposals/' + proposal['id'] + '/execute', headers=headers, json={
        'approval_digest': proposal['approval_digest'],
    })
    assert response.status_code == 400
    assert 'paused' in response.json()['detail'].lower() or 'crash' in response.json()['detail'].lower()
    saved = client.get('/api/agent/proposals/' + proposal['id'], headers=headers).json()
    assert saved['status'] == 'proposed' and saved.get('run_id') is None


def test_run_and_evidence_expose_hashable_recorded_provenance(client, headers):
    project, run_id, asset = _base_run(client, headers)
    evaluation_id = uid()
    with Session.begin() as db:
        db.get(Run, run_id).result = {
            'baseline_asset_id': asset['id'],
            'best_asset_id': asset['id'],
            'baseline_evaluation_id': evaluation_id,
            'best_evaluation_id': evaluation_id,
        }
        db.add(Evaluation(
            id=evaluation_id,
            asset_id=asset['id'],
            cache_key=uid().replace('-', '')[:64].ljust(64, '0'),
            evaluator='fixture',
            profile='fixture-profile',
            evidence={'shape': [1, 20484], 'scope': 'fixture evidence'},
            duration_seconds=0,
        ))
        db.add(Experiment(
            id=uid(),
            run_id=run_id,
            sequence=1,
            operator='brightness_up',
            hypothesis='bounded fixture intervention',
            specification={'version': 'intervention-proposal/v1', 'operator': 'brightness_up'},
            asset_id=asset['id'],
            decision='reverted',
            evidence={'evaluation_id': evaluation_id, 'meaning': 'fixture only'},
        ))
    run = client.get('/api/runs/' + run_id, headers=headers)
    assert run.status_code == 200, run.text
    provenance = run.json()['provenance']
    assert provenance['contract'] == 'run-provenance/v1'
    assert provenance['evaluations'][0]['id'] == evaluation_id
    assert provenance['experiments'][0]['evaluation_ids'] == [evaluation_id]
    assert len(provenance['evaluations'][0]['evidence_digest']) == 64
    evidence = client.get('/api/evaluations/' + evaluation_id, headers=headers)
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()['provenance']['contract'] == 'evaluation-provenance/v1'
    assert 'prediction_path' not in evidence.json()


def test_external_agent_closed_loop_uses_recorded_fixture_evidence_only(client, headers, monkeypatch):
    _, base_run_id, _ = _base_run(client, headers)
    proposal = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': base_run_id,
        'operator': 'brightness_up',
        'hypothesis': 'A bounded brightness intervention may improve relative happiness evidence.',
    }).json()
    reviewed_intervention = proposal['specification']['intervention']
    reviewed_digest = proposal['specification']['agent_contract']['intervention_digest']
    assert reviewed_intervention['response_gap']['actual'] == .2
    queued = client.post('/api/agent/proposals/' + proposal['id'] + '/execute', headers=headers, json={
        'approval_digest': proposal['approval_digest'],
    })
    assert queued.status_code == 200, queued.text
    run_id = queued.json()['id']
    with Session.begin() as db:
        run = db.get(Run, run_id)
        run.status = 'running'
        run.started_at = now()

    from neuroloop import worker

    calls = {'count': 0}

    def fake_evaluation(identity, selected, config):
        calls['count'] += 1
        value = .1 if calls['count'] == 1 else .8
        item = Evaluation(
            id=uid(),
            asset_id=selected.id,
            cache_key=uid().replace('-', '').ljust(64, '0'),
            evaluator='fixture',
            profile='fixture-profile',
            evidence={'response_ensemble': {
                'profile': 'fixture-profile',
                'values': {'happiness': value},
                'sources': {},
                'source_weights': {},
                'active_sources': ['fixture'],
                'disagreement': {},
                'mean_disagreement': None,
                'confidence': 'fixture',
                'interpretation': 'Deterministic control-flow fixture, not model output.',
            }},
            prediction_path=None,
            duration_seconds=0,
        )
        with Session.begin() as db:
            db.add(item)
        return item

    monkeypatch.setattr(worker, 'evaluation', fake_evaluation)
    monkeypatch.setattr(worker, 'render_candidate', lambda *args, **kwargs: worker.get_asset(args[2].id))
    monkeypatch.setattr(worker, 'planner_proposal', lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, 'record_evidence', lambda *args, **kwargs: None)
    monkeypatch.setattr(worker.CreativeStrategist, 'propose_candidates', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('approved intervention was regenerated')))

    worker.process(run_id)
    result = client.get('/api/runs/' + run_id, headers=headers)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['status'] == 'completed'
    assert calls['count'] == 2
    assert data['result']['best_metric']['value'] > data['result']['baseline_metric']['value']
    assert data['experiments'][0]['decision'] == 'kept'
    assert data['experiments'][0]['specification']['intervention'] == reviewed_intervention
    assert data['experiments'][0]['specification']['intervention_digest'] == reviewed_digest
    assert data['provenance']['contract'] == 'run-provenance/v1'
    assert data['provenance']['experiments'][0]['intervention_digest'] == reviewed_digest
    assert len(data['provenance']['evaluations']) == 2


def test_mcp_agent_tools_publish_stable_bounded_schemas():
    from neuroloop.mcp_server import mcp

    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    proposal = tools['propose_agent_experiment'].parameters['properties']
    assert proposal['operator']['enum'] == [
        'contrast_up', 'contrast_down', 'brightness_up', 'brightness_down',
        'saturation_up', 'saturation_down', 'headline_early', 'headline_late',
    ]
    assert proposal['source']['enum'] == ['ARIA', 'W&B MCP', 'local agent']
    execute = tools['execute_agent_proposal'].parameters['properties']['approval_digest']
    assert execute['pattern'] == '^[a-f0-9]{64}$'
    run = tools['run_experiment'].parameters['properties']
    assert run['max_evaluations']['maximum'] == 4
    assert run['max_seconds']['maximum'] == 900


def test_agent_cannot_escape_declared_operator_or_iteration_budget(client, headers):
    _, run_id, _ = _base_run(client, headers)
    outside = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'headline_early',
        'hypothesis': 'Test a bounded evidence intervention.',
    })
    assert outside.status_code == 400
    assert 'operator' in outside.json()['detail'].lower()

    with Session.begin() as db:
        run = db.get(Run, run_id)
        run.config = {**run.config, 'agent_contract': {
            'iteration': 4,
            'workflow': {
                'root_run_id': run_id,
                'max_iterations': 4,
                'max_evaluations': 12,
                'max_seconds': 7200,
                'allowed_operators': ['brightness_up'],
            },
        }}
    exhausted = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'brightness_up',
        'hypothesis': 'Test a bounded evidence intervention.',
    })
    assert exhausted.status_code == 400
    assert 'iteration budget' in exhausted.json()['detail'].lower()


def test_uncertain_proposal_state_is_visible_and_not_retried(client, headers):
    _, run_id, _ = _base_run(client, headers)
    proposal = client.post('/api/agent/proposals', headers=headers, json={
        'base_run_id': run_id,
        'operator': 'brightness_up',
        'hypothesis': 'Test a bounded evidence intervention.',
    }).json()
    with Session.begin() as db:
        from sqlalchemy import text
        db.execute(text("UPDATE agent_proposals SET status='executing' WHERE id=:id"), {'id': proposal['id']})
    visible = client.get('/api/agent/proposals/' + proposal['id'], headers=headers)
    assert visible.status_code == 200
    assert visible.json()['recovery']['state'] == 'outcome_uncertain'
    retry = client.post('/api/agent/proposals/' + proposal['id'] + '/execute', headers=headers, json={
        'approval_digest': proposal['approval_digest'],
    })
    assert retry.status_code == 400
    assert 'uncertain' in retry.json()['detail'].lower()


def test_workflow_proposal_claim_is_transactional_under_reentry(client, headers, monkeypatch):
    _, run_id, _ = _base_run(client, headers)
    from neuroloop import agent_bridge

    original_open = agent_bridge._open_proposal
    barrier = threading.Barrier(2)

    def synchronized_open(root_id, db=None):
        if db is None:
            barrier.wait(timeout=5)
        return original_open(root_id, db)

    monkeypatch.setattr(agent_bridge, '_open_proposal', synchronized_open)

    def submit(_):
        try:
            return agent_bridge.propose(agent_bridge.Proposal(
                base_run_id=run_id,
                operator='brightness_up',
                hypothesis='Test one bounded evidence intervention.',
            ))
        except Exception as exc:  # both outcomes are asserted below
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, range(2)))

    accepted = [item for item in outcomes if isinstance(item, dict)]
    rejected = [item for item in outcomes if isinstance(item, Exception)]
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert 'open agent proposal' in str(rejected[0]).lower()
    saved = agent_bridge.get_proposal(accepted[0]['id'])
    assert saved['status'] == 'proposed'
    assert saved['specification']['agent_contract']['budget_before']['evaluations_used'] == 0
