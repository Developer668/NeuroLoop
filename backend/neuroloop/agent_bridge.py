"""Small, typed bridge for one bounded external-agent continuation."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text

from . import services
from .db import Asset, Project, Run, Session, as_dict, emit, engine, now, uid
from .schemas import RunCreate
from .strategy import CreativeStrategist

AgentOperator = Literal[
    'contrast_up', 'contrast_down', 'brightness_up', 'brightness_down',
    'saturation_up', 'saturation_down', 'headline_early', 'headline_late',
]
AgentSource = Literal['ARIA', 'W&B MCP', 'local agent']

MAX_AGENT_ITERATIONS = 4
MAX_AGENT_EVALUATIONS = 12
MAX_AGENT_SECONDS = 7200
MAX_AGENT_RUN_EVALUATIONS = 4
MAX_AGENT_RUN_SECONDS = 900

_UNSAFE_HYPOTHESIS = re.compile(
    r"""(?ix)\b(?:https?|ftp)://|\bwww\.|(?:^|\s)[A-Za-z]:[\\/]|(?:^|\s)/(?:[^\s]|$)|(?:^|\s)(?:python|python3|bash|zsh|sh|powershell|pwsh|cmd|curl|wget|docker|git|sudo|rm|ffmpeg)(?:\s|$)|&&|\|\||[;&|<>`]"""
)
_UNSUPPORTED_CLAIM = re.compile(
    r"""(?ix)\b(?:purchase\s+probability|conversion\s+rate|click[- ]?through|\bctr\b|guarantee(?:d)?|human\s+(?:response|emotion|preference)|viewer\s+(?:will|would|feel)|(?:increase|improve|predict|cause|drive|maximize|optimize)\s+(?:sales|purchases|revenue|clicks))\b"""
)


def _safe_hypothesis(value: str) -> str:
    if _UNSAFE_HYPOTHESIS.search(value):
        raise ValueError('Hypothesis may contain only a bounded model-evidence intervention; URLs, paths and commands are not accepted')
    if _UNSUPPORTED_CLAIM.search(value):
        raise ValueError('Hypothesis must not claim human, business or purchase outcomes')
    return value


class Proposal(BaseModel):
    """Stable v1 input for a single typed intervention proposal."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, populate_by_name=True)

    version: Literal[1] = 1
    source: AgentSource = 'local agent'
    base_run_id: str = Field(min_length=1, max_length=120)
    operator: AgentOperator
    hypothesis: str = Field(min_length=1, max_length=1000)

    @field_validator('hypothesis')
    @classmethod
    def safe_hypothesis(cls, value: str) -> str:
        return _safe_hypothesis(value)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str, allow_nan=False)


def _read(identity: str) -> dict[str, Any]:
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 120:
        raise services.DomainError('A proposal ID is required')
    with engine.connect() as db:
        row = db.execute(text('SELECT * FROM agent_proposals WHERE id=:id'), {'id': identity}).mappings().first()
    if not row:
        raise services.DomainError('Agent proposal not found; inspect the project context for valid IDs')
    result = dict(row)
    try:
        result['specification'] = json.loads(result.pop('specification'))
    except (TypeError, json.JSONDecodeError) as exc:
        raise services.DomainError('Agent proposal provenance is unreadable; do not retry it') from exc
    return result


def _lineage(identity: str) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    with Session() as db:
        current = db.get(Run, identity)
        while current is not None:
            if current.id in seen:
                raise services.DomainError('Agent run lineage contains a cycle; no continuation is permitted')
            seen.add(current.id)
            chain.append(as_dict(current))
            contract = (current.config or {}).get('agent_contract') or {}
            parent = contract.get('parent_run_id')
            current = db.get(Run, parent) if isinstance(parent, str) else None
    return chain


def _workflow_runs(root_id: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the root and every managed continuation in the workflow."""
    with Session() as db:
        rows = list(db.scalars(select(Run)).all())
    runs = []
    for row in rows:
        contract = (row.config or {}).get('agent_contract') or {}
        workflow = contract.get('workflow') or {}
        if row.id == root_id or workflow.get('root_run_id') == root_id:
            runs.append(as_dict(row))
    return runs or fallback


def _workflow(chain: list[dict[str, Any]], request: RunCreate) -> dict[str, Any]:
    for item in reversed(chain):
        inherited = ((item.get('config') or {}).get('agent_contract') or {}).get('workflow')
        if isinstance(inherited, dict):
            return dict(inherited)
    snapshot = (chain[0].get('config') or {}).get('project_snapshot') or {}
    minimum = 2 + len(snapshot.get('reference_ids') or [])
    return {
        'version': 1,
        'root_run_id': chain[-1]['id'],
        'max_iterations': MAX_AGENT_ITERATIONS,
        'max_evaluations': min(MAX_AGENT_EVALUATIONS, max(int(request.max_evaluations), minimum) * MAX_AGENT_ITERATIONS),
        'max_seconds': min(MAX_AGENT_SECONDS, max(30, int(request.max_seconds)) * MAX_AGENT_ITERATIONS),
        'allowed_operators': list(request.operators),
    }


def _usage(chain: list[dict[str, Any]]) -> tuple[int, float]:
    return sum(int(item.get('evaluations_used') or 0) for item in chain), sum(float(item.get('compute_seconds') or 0) for item in chain)


def _open_proposal(root_run_id: str, db=None) -> bool:
    if db is None:
        with Session() as session:
            return _open_proposal(root_run_id, session)
    rows = db.execute(text("SELECT status,run_id,specification FROM agent_proposals WHERE status IN ('proposed','approved','executing','queued')")).mappings().all()
    linked_runs = {row['run_id']: db.get(Run, row['run_id']) for row in rows if row['status'] == 'queued' and row['run_id']}
    for row in rows:
        try:
            contract = json.loads(row['specification']).get('agent_contract', {})
        except (TypeError, json.JSONDecodeError):
            continue
        if (contract.get('workflow') or {}).get('root_run_id') != root_run_id:
            continue
        if row['status'] == 'queued':
            linked = linked_runs.get(row['run_id'])
            if linked is None or linked.status not in {'completed', 'failed', 'cancelled'}:
                return True
            continue
        if row['status'] in {'proposed', 'approved', 'executing'}:
            return True
    return False


def _starting_asset(base: dict[str, Any], snapshot: dict[str, Any]) -> Asset:
    root_id = snapshot.get('asset_id')
    allowed = {root_id} if isinstance(root_id, str) else set()
    result = base.get('result') or {}
    preferred = result.get('best_asset_id') or root_id
    for experiment in base.get('experiments') or []:
        if experiment.get('decision') == 'kept' and isinstance(experiment.get('asset_id'), str):
            allowed.add(experiment['asset_id'])
    inherited = ((base.get('config') or {}).get('agent_contract') or {}).get('starting_asset_id')
    if isinstance(inherited, str):
        allowed.add(inherited)
    if not isinstance(preferred, str) or preferred not in allowed:
        raise services.DomainError('The prior run has no validated managed winner to use as a continuation')
    with Session() as db:
        asset = db.get(Asset, preferred)
        if asset is None:
            raise services.DomainError('The prior run winner no longer exists; continuation cannot start')
        return asset


def _intervention(body: Proposal, base: dict[str, Any], request: RunCreate, snapshot: dict[str, Any]) -> dict[str, Any]:
    target = request.target.model_dump(mode='json') if request.target is not None else None
    result = base.get('result') or {}
    typed = CreativeStrategist().propose(
        target,
        result.get('best_response') or result.get('baseline_response') or {},
        {},
        [],
        snapshot.get('constraints') or {},
        allowed_operators=[body.operator],
        seed='external-agent:' + base['id'],
        lineage_id='agent:' + base['id'],
    )
    if typed is None:
        raise services.DomainError('No deterministic typed intervention is available for the recorded evidence')
    return typed.model_copy(update={'hypothesis': body.hypothesis}).as_dict()


def propose(body: Proposal) -> dict[str, Any]:
    base = services.get_run(body.base_run_id)
    if base['mode'] != 'optimize' or base['status'] not in {'completed', 'failed'}:
        raise services.DomainError('A completed or failed controlled optimization is required as context; cancelled runs are not replayed')
    config = base.get('config') or {}
    snapshot = config.get('project_snapshot')
    if not isinstance(snapshot, dict) or not snapshot.get('asset_id'):
        raise services.DomainError('The base run has no frozen project contract to continue')
    chain = _lineage(base['id'])
    root = chain[-1]['id']
    request = RunCreate.model_validate(config.get('request') or {})
    workflow = _workflow(chain, request)
    if workflow.get('root_run_id') != root:
        raise services.DomainError('Agent lineage root does not match the frozen run contract')
    workflow_runs = _workflow_runs(root, chain)
    if _open_proposal(root):
        raise services.DomainError('This run already has an open agent proposal; review or execute it before submitting another')
    iteration = max((int(((item.get('config') or {}).get('agent_contract') or {}).get('iteration') or 0) for item in workflow_runs), default=0) + 1
    if iteration > int(workflow.get('max_iterations', MAX_AGENT_ITERATIONS)):
        raise services.DomainError('Agent iteration budget is exhausted; start a new declared run')
    allowed = list(workflow.get('allowed_operators') or request.operators)
    if body.operator not in allowed:
        raise services.DomainError('Proposal operator is outside the original permitted operator set')
    used_evaluations, used_seconds = _usage(workflow_runs)
    budget_evaluations = int(workflow.get('max_evaluations', MAX_AGENT_EVALUATIONS))
    budget_seconds = float(workflow.get('max_seconds', MAX_AGENT_SECONDS))
    remaining_evaluations = budget_evaluations - used_evaluations
    minimum = 2 + (len(snapshot.get('reference_ids') or []) if request.objective == 'reference_similarity' else 0)
    next_evaluations = min(MAX_AGENT_RUN_EVALUATIONS, request.max_evaluations, remaining_evaluations)
    if next_evaluations < minimum:
        raise services.DomainError(f'Agent evaluation budget has {max(0, remaining_evaluations)} remaining; at least {minimum} are required for one bounded intervention')
    remaining_seconds = budget_seconds - used_seconds
    next_seconds = min(MAX_AGENT_RUN_SECONDS, request.max_seconds, int(remaining_seconds))
    if next_seconds < 30:
        raise services.DomainError('Agent time budget is exhausted; start a new declared run')
    starting = _starting_asset(base, snapshot)
    next_request = request.model_copy(update={'operators': [body.operator], 'hypothesis': body.hypothesis, 'max_evaluations': next_evaluations, 'max_seconds': next_seconds})
    identity = uid()
    contract = {
        'version': 1,
        'source': body.source,
        'proposal_id': identity,
        'root_run_id': root,
        'parent_run_id': base['id'],
        'iteration': iteration,
        'workflow': {
            'version': 1,
            'root_run_id': root,
            'max_iterations': int(workflow.get('max_iterations', MAX_AGENT_ITERATIONS)),
            'max_evaluations': budget_evaluations,
            'max_seconds': budget_seconds,
            'allowed_operators': allowed,
        },
        'budget_before': {'evaluations_used': used_evaluations, 'seconds_used': used_seconds, 'remaining_evaluations': remaining_evaluations, 'remaining_seconds': remaining_seconds},
        'starting_asset_id': starting.id,
        'starting_asset_sha256': starting.sha256,
        'starting_asset_snapshot': services._public_asset(starting),
        'asset_metadata_snapshots': config.get('asset_metadata_snapshots') or {},
        'objective': config.get('objective'),
        'constraints': snapshot.get('constraints') or {},
    }
    intervention = _intervention(body, base, request, snapshot)
    contract['intervention'] = intervention
    contract['intervention_digest'] = hashlib.sha256(_canonical(intervention).encode('utf-8')).hexdigest()
    specification = {'contract': 'agent-closed-loop/v1', 'version': 1, 'owner': 'authenticated-workspace', 'proposal': body.model_dump(mode='json'), 'request': next_request.model_dump(mode='json'), 'project_snapshot': snapshot, 'agent_contract': contract, 'intervention': intervention}
    encoded = _canonical(specification)
    # Lock the root run before rechecking and inserting. SQLite serializes the
    # write transaction; PostgreSQL takes a row lock on the same root.
    with Session.begin() as db:
        locked = db.execute(text('UPDATE runs SET heartbeat=heartbeat WHERE id=:id'), {'id': root}).rowcount
        if locked != 1:
            raise services.DomainError('The workflow root no longer exists; no proposal was stored')
        if _open_proposal(root, db):
            raise services.DomainError('This run already has an open agent proposal; review or execute it before submitting another')
        db.execute(text('INSERT INTO agent_proposals(id,version,source,specification,created_at) VALUES (:id,1,:source,:spec,:t)'), {'id': identity, 'source': body.source, 'spec': encoded, 't': now()})
    emit(base['id'], 'agent_proposal', 'Stored a typed external intervention under the frozen run contract.', proposal_id=identity, iteration=iteration, operator=body.operator)
    return get_proposal(identity)


def get_proposal(identity: str) -> dict[str, Any]:
    record = _read(identity)
    result = {key: value for key, value in record.items() if key != 'specification'}
    result['specification'] = record['specification']
    result['approval_digest'] = hashlib.sha256(_canonical(record['specification']).encode('utf-8')).hexdigest()
    if record['status'] == 'executing' and not record.get('run_id'):
        result['recovery'] = {'state': 'outcome_uncertain', 'action': 'Inspect the proposal and run queue; do not retry blindly.'}
    elif record.get('run_id'):
        result['run'] = services.get_run(record['run_id'])
    return result


def _assert_project(specification: dict[str, Any]) -> None:
    with Session() as db:
        project = db.get(Project, specification['request']['project_id'])
        if project is None:
            raise services.DomainError('Project no longer exists; the proposal cannot be executed')
        if as_dict(project) != specification['project_snapshot']:
            raise services.DomainError('Project changed since proposal approval; create a fresh local experiment first')


def _assert_budget(specification: dict[str, Any]) -> None:
    contract = specification.get('agent_contract') or {}
    parent = contract.get('parent_run_id')
    workflow = contract.get('workflow') or {}
    chain = _lineage(parent) if isinstance(parent, str) else []
    if not chain or chain[-1]['id'] != workflow.get('root_run_id'):
        raise services.DomainError('Proposal lineage no longer matches the declared workflow')
    runs = _workflow_runs(workflow.get('root_run_id', chain[-1]['id']), chain)
    evaluations, seconds = _usage(runs)
    if evaluations >= int(workflow.get('max_evaluations', MAX_AGENT_EVALUATIONS)):
        raise services.DomainError('Agent evaluation budget was consumed before approval; start a new declared workflow')
    if seconds >= float(workflow.get('max_seconds', MAX_AGENT_SECONDS)):
        raise services.DomainError('Agent time budget was consumed before approval; start a new declared workflow')


def _run_for_key(key: str) -> dict[str, Any] | None:
    with Session() as db:
        item = db.scalar(select(Run).where(Run.idempotency_key == key))
        return as_dict(item) if item is not None else None


def execute(identity: str, expected_digest: str) -> dict[str, Any]:
    record = get_proposal(identity)
    if not isinstance(expected_digest, str) or not hmac.compare_digest(expected_digest, record['approval_digest']):
        raise services.DomainError('Approval digest does not match the reviewed proposal; fetch the proposal again and review its exact contract')
    if record.get('run_id'):
        return services.get_run(record['run_id'])
    if record['status'] == 'executing':
        existing = _run_for_key('agent-proposal/' + identity)
        if existing:
            with engine.begin() as db:
                db.execute(text("UPDATE agent_proposals SET status='queued',run_id=:run WHERE id=:id AND status='executing' AND run_id IS NULL"), {'id': identity, 'run': existing['id']})
            return services.get_run(existing['id'])
        raise services.DomainError('Proposal execution outcome is uncertain; inspect its recovery state and run queue before retrying')
    if record['status'] not in {'proposed', 'approved'}:
        raise services.DomainError(f"Proposal is in terminal state {record['status']!r}; no replay is permitted")
    previous = record['status']
    with engine.begin() as db:
        claimed = db.execute(text("UPDATE agent_proposals SET status='executing' WHERE id=:id AND status IN ('proposed','approved') AND run_id IS NULL"), {'id': identity}).rowcount == 1
    if not claimed:
        latest = get_proposal(identity)
        if latest.get('run_id'):
            return services.get_run(latest['run_id'])
        raise services.DomainError('Proposal is being executed by another worker; inspect it before retrying')
    specification = record['specification']
    try:
        _assert_project(specification)
        _assert_budget(specification)
        run = services.create_run(RunCreate.model_validate(specification['request']), 'agent-proposal/' + identity, expected_project=specification['project_snapshot'], agent_contract=specification['agent_contract'])
    except services.DomainError:
        with engine.begin() as db:
            db.execute(text('UPDATE agent_proposals SET status=:status WHERE id=:id AND status=\'executing\' AND run_id IS NULL'), {'status': previous, 'id': identity})
        raise
    except Exception as exc:
        raise services.DomainError('Proposal execution outcome is uncertain; inspect the proposal and run queue before retrying (' + type(exc).__name__ + ')') from exc
    with engine.begin() as db:
        changed = db.execute(text("UPDATE agent_proposals SET status='queued',run_id=:run WHERE id=:id AND status='executing' AND run_id IS NULL"), {'id': identity, 'run': run['id']}).rowcount
    if changed != 1:
        raise services.DomainError('Proposal state changed while queuing; inspect the proposal and run before retrying')
    emit(specification['agent_contract']['parent_run_id'], 'agent_run_queued', 'Queued the reviewed external-agent continuation through the shared run service.', proposal_id=identity, continuation_run_id=run['id'])
    return services.get_run(run['id'])
