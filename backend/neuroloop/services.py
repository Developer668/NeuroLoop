"""Shared domain services used by HTTP, MCP and the run worker."""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from sqlalchemy import select, func
from .config import settings
from .db import Session, Asset, Project, Run, Evaluation, Experiment, RunEvent, ArchivedRecord, as_dict, uid, now
from .schemas import ProjectCreate, RunCreate, CreativeCreate
from .media import inspect_media, thumbnail, digest, compose, SUFFIXES
from .constraints import ConstraintError, CreativeConstraints

class DomainError(ValueError):
    pass


def _digest(value: object) -> str:
    """Digest JSON-serializable contract data without exposing local paths."""
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), default=str, allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _public_asset(record: Asset) -> dict:
    """Return an asset record suitable for an agent contract.

    The managed path is deliberately omitted. Asset metadata is still useful
    provenance, but an external agent never gets a filesystem target or a URL
    to reinterpret as an execution instruction.
    """
    value = as_dict(record, ('path',))
    details = dict(value.get('details') or {})
    for key in ('path', 'source_path', 'prediction_path', 'command', 'url'):
        details.pop(key, None)
    value['details'] = details
    return value


def capabilities() -> dict:
    s=settings(); root=s.root
    assets=[('TRIBE brain weights',root/'tribev2-balanced-qv-local/best.ckpt'),('INT8 video encoder',root/'tribev2-balanced-qv-local/quantized_video/model.safetensors'),('NF4 text encoder',root/'models/text/llama-3.2-3b-unsloth-q4/model.safetensors'),('Audio encoder',root/'models/audio/w2v-bert-2.0/model.safetensors')]
    with Session() as db:
        latest=db.scalar(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(1))
        verification={'evaluation_id':latest.id,'profile':latest.profile,'created_at':latest.created_at} if latest else None
    from .execution_guard import execution_status
    from .kragel import status as kragel_status
    from .generation import statuses as generation_statuses
    return {'product':'NeuroLoop','version':'0.1.0','execution':execution_status(),'deployment':'single-workspace authenticated local service','training':False,'models':[{'name':name,'status':'downloaded' if path.is_file() else 'missing'} for name,path in assets],
      'tribe':{'status':'weights_present' if all(p.is_file() for _,p in assets) else 'missing_weights','last_technical_test':verification,'meaning':'Predicted average-subject cortical response; not thoughts or purchase intent.'},
      'tsam':{'status':'experimental_weights_present' if (root/'models/emotion/tsam/weights/tsam_weights.tar').is_file() else 'missing_weights','reason':'Independent CPU audiovisual readout. The staged macOS model runtime now includes its pinned dependencies; each requested evaluation still fails closed if strict checkpoint loading or preprocessing fails. Outputs are uncalibrated relative evidence.'},
      'kragel':kragel_status(),
      'generation_providers':generation_statuses(),
      'modalities':{'video':'neural analysis and bounded controlled edits','image':'explicit experimental repeated-frame presentation','audio':'audio response; local speech transcription or supplied timed words','text':'requires explicit timed-word transcript'},
      'asr':{'status':'available' if (root/'models/preprocessing/faster-whisper-small/model.bin').exists() else 'not_installed','purpose':'Speech preprocessing only; not another content judge.'},
      'integrations':[
        {'name':'Weights & Biases Weave','status':'configured' if s.weave_enabled and bool(os.getenv('WANDB_API_KEY')) else 'not_configured','purpose':'Experiment trace and metric provenance'},
        {'name':'W&B Inference','status':'configured' if s.planner_enabled and bool(os.getenv('WANDB_API_KEY')) else 'not_configured','purpose':'Optional structured experiment planner'},
        {'name':'ARIA / W&B Launch','status':'check_live_connection','purpose':'Versioned, locally approved jobs; check the live agent and inspect each result receipt'},
        {'name':'CoreWeave ARIA','status':'reviewed_optional','purpose':'Reviewed real experiment history; cloud access is optional for local inference'},
        {'name':'CoreWeave','status':'awaiting_sponsor_credits','purpose':'Cloud compute for future generation/inference; no cloud resource is claimed as configured'},
        {'name':'marimo','status':'check_live_connection','purpose':'Read-only recorded evidence. Check service connections for the current HTTP response'},
        {'name':'W&B Models','status':'research_metadata','purpose':'Stores experiment metadata used by research/Launch workflows'},
        {'name':'W&B MCP','status':'credential_required_per_partner','purpose':'Official read-only inspection of W&B records'},
        {'name':'TypeSafe','status':'disabled','purpose':'Future DecisionProvider interface only'}],
      'limits':{'upload_bytes':s.max_upload_bytes,'media_seconds':s.max_media_seconds,'max_evaluations_per_run':12},
      'claim_boundaries':['No measured human subjects','No CTR or purchase probability','No psychological decoder validated on these synthetic predictions','No model-weight training'],
      'model_downloads_automatic':False}

def register_asset(path: Path,name: str,kind: str,extra: dict | None=None) -> dict:
    try:
        details=inspect_media(path,kind)
    except (OSError, UnicodeError) as exc:
        from .media import MediaError
        raise MediaError('The uploaded file cannot be decoded as the declared media type') from exc
    if extra: details.update(extra)
    identity=uid(); preview=settings().data/'assets'/f'{identity}.preview.jpg'
    if thumbnail(path,kind,preview): details['preview']=preview.name
    with Session.begin() as db:
        asset=Asset(id=identity,name=name,kind=kind,sha256=digest(path),path=str(path),size=path.stat().st_size,details=details)
        db.add(asset)
    return as_dict(asset,('path',))

def create_project(body: ProjectCreate) -> dict:
    with Session.begin() as db:
        for identity in ([body.asset_id] if body.asset_id else [])+body.reference_ids:
            if not db.get(Asset,identity): raise DomainError('A selected asset does not exist')
        if body.asset_id in body.reference_ids: raise DomainError('The original cannot be its own reference')
        item=Project(**body.model_dump()); db.add(item); db.flush()
        return as_dict(item)


def get_project(identity: str) -> dict:
    """Read a project contract through the same ownership boundary as the API."""
    with Session() as db:
        item = db.get(Project, identity)
        if item is None:
            raise DomainError('Project not found')
        return as_dict(item)


def project_context(identity: str) -> dict:
    """Return the bounded, read-only context an external agent may inspect.

    This is intentionally a view over persisted records, not a second project
    model. Briefs and constraints are copied from the project snapshot; assets
    are represented by managed IDs, hashes and inspected metadata only.
    """
    with Session() as db:
        project = db.get(Project, identity)
        if project is None:
            raise DomainError('Project not found')
        asset_ids = list(dict.fromkeys(([project.asset_id] if project.asset_id else []) + list(project.reference_ids or [])))
        assets = {item.id: _public_asset(item) for item in (db.get(Asset, asset_id) for asset_id in asset_ids) if item is not None}
        runs = db.scalars(select(Run).where(Run.project_id == identity).order_by(Run.created_at.desc()).limit(50)).all()
        return {
            'contract': 'project-context/v1',
            'project': as_dict(project),
            'brief': project.brief,
            'constraints': dict(project.constraints or {}),
            'original': assets.get(project.asset_id) if project.asset_id else None,
            'references': [assets[asset_id] for asset_id in project.reference_ids or [] if asset_id in assets],
            'runs': [
                {
                    'id': item.id,
                    'status': item.status,
                    'mode': item.mode,
                    'stage': item.stage,
                    'evaluations_used': item.evaluations_used,
                    'max_evaluations': item.max_evaluations,
                    'compute_seconds': item.compute_seconds,
                    'created_at': item.created_at,
                    'finished_at': item.finished_at,
                }
                for item in runs
            ],
            'claim_boundaries': [
                'Stored model evidence is not a measured human response.',
                'Relative scores are not purchase, click-through, conversion or emotion probabilities.',
                'Only managed asset IDs and fixed operators can enter an execution contract.',
            ],
        }

def update_project(identity: str,body: ProjectCreate) -> dict:
    with Session.begin() as db:
        item=db.get(Project,identity)
        if item is None: raise DomainError('Project not found')
        for asset_id in ([body.asset_id] if body.asset_id else [])+body.reference_ids:
            if not db.get(Asset,asset_id): raise DomainError('Asset not found')
        if body.asset_id in body.reference_ids: raise DomainError('Original and reference must differ')
        for key,value in body.model_dump().items(): setattr(item,key,value)
        return as_dict(item)

def create_run(body: RunCreate, key: str | None = None, expected_project: dict | None = None,
               agent_contract: dict | None = None) -> dict:
    """Validate and queue one immutable run contract.

    HTTP, MCP and the external-agent bridge all come through this function.
    ``agent_contract`` is metadata supplied by the bridge; it cannot change
    the objective or execute anything by itself.
    """
    from .execution_guard import execution_status
    if execution_status()['paused']:
        raise DomainError('Model execution is paused after a Windows graphics crash. Saved results remain available. Resolve the crash investigation before enabling another GPU run.')
    key=key or uid()
    if len(key)>100: raise DomainError('Idempotency key is too long')
    with Session.begin() as db:
        existing=db.scalar(select(Run).where(Run.idempotency_key==key))
        if existing:
            if existing.config.get('request')!=body.model_dump(): raise DomainError('Idempotency key was already used for a different request')
            return as_dict(existing)
        project=db.get(Project,body.project_id)
        if project is None or not project.asset_id: raise DomainError('Choose an original asset before starting a run')
        if expected_project is not None and as_dict(project)!=expected_project:
            raise DomainError('Project changed since proposal approval')
        original=db.get(Asset,project.asset_id)
        if original is None: raise DomainError('Original asset not found')
        if original.kind=='image' and not body.allow_static_presentation:
            raise DomainError('Enable experimental static-image presentation to analyze images with TRIBE')
        if original.kind=='text' and not (body.transcript or original.details.get('transcript')):
            raise DomainError('Text requires a timed-word transcript; no external TTS is called automatically')
        if body.mode=='compare' and not project.reference_ids:
            raise DomainError('Choose at least one reference for comparison')
        if body.mode=='optimize' and body.objective=='reference_similarity' and not project.reference_ids:
            raise DomainError('Choose at least one reference for the reference-similarity objective')
        if body.mode=='optimize' and original.kind not in {'video','image'}:
            raise DomainError('Controlled optimization currently requires visual content')
        if len(set(project.reference_ids)) != len(project.reference_ids):
            raise DomainError('Reference assets must be unique')
        if body.mode=='optimize' and not body.operators:
            raise DomainError('Select at least one permitted edit operator')
        if body.mode=='optimize' and all(x.startswith('headline_') for x in body.operators) and not original.details.get('composition'):
            raise DomainError('Headline timing requires an editable composition, not a flattened video')
        if body.mode=='optimize' and project.constraints.get('preserve_duration', True) is not True:
            raise DomainError('The current operators preserve duration; changing duration is unsupported')
        try:
            CreativeConstraints.from_mapping(project.constraints)
        except ConstraintError as exc:
            raise DomainError(str(exc)) from exc
        if project.constraints.get('locked_copy') and not original.details.get('composition'):
            raise DomainError('Exact-copy locking requires an editable composition with a known text layer')
        if type(project.constraints.get('max_filter_edits',2)) is not int or not 0<=project.constraints.get('max_filter_edits',2)<=4:
            raise DomainError('max_filter_edits must be an integer between 0 and 4')
        for field in ['preserve_duration','preserve_audio']:
            if field in project.constraints and not isinstance(project.constraints[field],bool):
                raise DomainError(field+' must be boolean')
        active_refs=project.reference_ids if body.objective=='reference_similarity' or body.mode=='compare' else []
        required=1+len(active_refs)
        if body.max_evaluations<required:
            raise DomainError(f'The baseline and references require a budget of at least {required} evaluations')
        for ref_id in active_refs:
            ref=db.get(Asset,ref_id)
            if not ref: raise DomainError('Reference asset no longer exists')
            if ref.sha256==original.sha256: raise DomainError('A reference cannot be a duplicate of the original')
            if ref.kind != original.kind:
                raise DomainError('Reference and original must use the same source modality for this comparison')
            if ref.kind=='text':
                raise DomainError('Cross-document timed-text comparison needs per-document timing; analyze documents individually first')
        asr_ready=(settings().root/'models/preprocessing/faster-whisper-small/model.bin').is_file()
        for media_id in [original.id]+active_refs:
            selected=db.get(Asset,media_id)
            words=(body.transcript or selected.details.get('transcript',[])) if media_id==original.id else selected.details.get('transcript',[])
            if selected.details.get('has_audio') and not body.no_speech and not words and not asr_ready:
                raise DomainError('Speech preprocessing is unavailable. Supply timed words for each spoken asset, or explicitly confirm all inputs contain no speech.')
        snapshots={media_id:dict(db.get(Asset,media_id).details) for media_id in [original.id]+active_refs}
        objective='response-target-distance/v1' if body.objective=='response_target' else 'spatially-centered-cosine/eight-normalized-time-bins/v1'
        config={'request':body.model_dump(),'project_snapshot':as_dict(project),'asset_metadata_snapshots':snapshots,'objective':objective}
        if agent_contract is not None:
            if not isinstance(agent_contract, dict):
                raise DomainError('Agent run metadata must be an object')
            expected_snapshots = agent_contract.get('asset_metadata_snapshots')
            if expected_snapshots is not None:
                if not isinstance(expected_snapshots, dict):
                    raise DomainError('Agent asset provenance must be an object')
                for asset_id, expected in expected_snapshots.items():
                    selected = db.get(Asset, asset_id)
                    if selected is None or dict(selected.details or {}) != dict(expected or {}):
                        raise DomainError('An approved source asset changed since the proposal was reviewed')
            # Only the already validated bridge can provide this metadata. A
            # starting asset is still checked here so an ID can never become
            # an arbitrary filesystem or URL target.
            starting_asset_id = agent_contract.get('starting_asset_id')
            if starting_asset_id is not None:
                starting = db.get(Asset, starting_asset_id)
                if starting is None:
                    raise DomainError('The approved continuation asset no longer exists')
                if starting.kind != original.kind:
                    raise DomainError('The approved continuation asset has a different source modality')
                expected_start = agent_contract.get('starting_asset_snapshot')
                if isinstance(expected_start, dict) and _public_asset(starting) != expected_start:
                    raise DomainError('The approved continuation asset changed since the proposal was reviewed')
                contract = dict(agent_contract)
                contract['starting_asset_snapshot'] = _public_asset(starting)
                config['starting_asset_id'] = starting.id
                config['agent_contract'] = contract
            else:
                config['agent_contract'] = dict(agent_contract)
        run=Run(project_id=project.id,mode=body.mode,max_evaluations=body.max_evaluations,config=config,idempotency_key=key)
        db.add(run); db.flush(); db.add(RunEvent(run_id=run.id,kind='queued',message='Run queued with a fixed objective and evaluation budget.',details={'budget':body.max_evaluations}))
        return as_dict(run)

def _evaluation_ids(value: object) -> set[str]:
    """Collect only explicit evaluation references from persisted evidence."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if (key == 'evaluation_id' or key.endswith('_evaluation_id')) and isinstance(item, str):
                found.add(item)
            elif key.endswith('_evaluation_ids') and isinstance(item, list):
                found.update(entry for entry in item if isinstance(entry, str))
            else:
                found.update(_evaluation_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_evaluation_ids(item))
    return found


def _provenance(row: Run, experiments: list[Experiment], evaluations: list[Evaluation], assets: dict[str, Asset]) -> dict:
    request = (row.config or {}).get('request', {})
    experiment_rows = []
    for experiment in experiments:
        evidence_ids = sorted(_evaluation_ids(experiment.evidence or {}))
        specification = experiment.specification or {}
        intervention = specification.get('intervention') if isinstance(specification.get('intervention'), dict) else specification
        experiment_rows.append({
            'id': experiment.id,
            'sequence': experiment.sequence,
            'operator': experiment.operator,
            'decision': experiment.decision,
            'asset_id': experiment.asset_id,
            'specification_digest': _digest(specification),
            'intervention_digest': specification.get('intervention_digest') or _digest(intervention),
            'evidence_digest': _digest(experiment.evidence or {}),
            'evaluation_ids': evidence_ids,
        })
    evaluation_rows = []
    for evaluation in evaluations:
        evaluation_rows.append({
            'id': evaluation.id,
            'asset_id': evaluation.asset_id,
            'asset_sha256': assets[evaluation.asset_id].sha256 if evaluation.asset_id in assets else None,
            'cache_key': evaluation.cache_key,
            'evaluator': evaluation.evaluator,
            'profile': evaluation.profile,
            'evidence_digest': _digest(evaluation.evidence or {}),
            'created_at': evaluation.created_at,
        })
    return {
        'contract': 'run-provenance/v1',
        'run_id': row.id,
        'project_id': row.project_id,
        'request_digest': _digest(request),
        'config_digest': _digest(row.config or {}),
        'objective': (row.config or {}).get('objective'),
        'agent_contract': (row.config or {}).get('agent_contract'),
        'experiments': experiment_rows,
        'evaluations': evaluation_rows,
        'immutability': 'IDs, hashes, evaluator profiles and recorded evidence are observations; no missing output is inferred.',
    }


def get_run(identity: str) -> dict:
    with Session() as db:
        row=db.get(Run,identity)
        if not row: raise DomainError('Run not found')
        experiments=list(db.scalars(select(Experiment).where(Experiment.run_id==identity).order_by(Experiment.sequence)))
        events=[as_dict(x) for x in db.scalars(select(RunEvent).where(RunEvent.run_id==identity).order_by(RunEvent.id))]
        ids=_evaluation_ids(row.result or {})
        ids.update(_evaluation_ids([item.evidence for item in experiments]))
        evaluations=[db.get(Evaluation,evaluation_id) for evaluation_id in sorted(ids)]
        evaluations=[item for item in evaluations if item is not None]
        assets={item.id:item for item in (db.get(Asset,evaluation.asset_id) for evaluation in evaluations) if item is not None}
        result=as_dict(row)
        result['experiments']=[as_dict(x) for x in experiments]
        result['events']=events
        result['provenance']=_provenance(row,experiments,evaluations,assets)
        return result


def get_evidence(identity: str) -> dict:
    """Return persisted evidence plus identity hashes, never a fabricated array."""
    with Session() as db:
        item=db.get(Evaluation, identity)
        if item is None:
            raise DomainError('Evaluation not found')
        result=as_dict(item, ('prediction_path',))
        asset=db.get(Asset,item.asset_id)
        result['provenance']={
            'contract':'evaluation-provenance/v1',
            'evaluation_id':item.id,
            'asset_id':item.asset_id,
            'asset_sha256':asset.sha256 if asset else None,
            'cache_key':item.cache_key,
            'evidence_digest':_digest(item.evidence or {}),
            'meaning':'Persisted model evidence only; no human-response or purchase claim.',
        }
        return result

def cancel_run(identity: str) -> dict:
    with Session.begin() as db:
        row=db.get(Run,identity)
        if not row: raise DomainError('Run not found')
        if row.status in {'queued','running'}:
            row.cancel_requested=1
            if row.status=='queued': row.status='cancelled';row.finished_at=now();row.stop_reason='Cancelled before work started'
            db.add(RunEvent(run_id=identity,kind='cancel_requested',message='Cancellation requested; any in-flight model call ends at a safe checkpoint.'))
        return as_dict(row)

def dashboard() -> dict:
    with Session() as db:
        def visible(model,kind):
            return select(model).where(model.id.not_in(select(ArchivedRecord.record_id).where(ArchivedRecord.kind==kind)))
        projects=db.scalars(visible(Project,'project').order_by(Project.created_at.desc())).all()
        assets=db.scalars(visible(Asset,'asset').order_by(Asset.created_at.desc()).limit(100)).all()
        runs=db.scalars(visible(Run,'run').order_by(Run.created_at.desc()).limit(100)).all()
        evaluations=db.scalars(visible(Evaluation,'evaluation').order_by(Evaluation.created_at.desc()).limit(100)).all()
        asset_count=db.scalar(select(func.count()).select_from(visible(Asset,'asset').subquery()))
        evaluation_count=db.scalar(select(func.count()).select_from(visible(Evaluation,'evaluation').subquery()))
        experiment_count=db.scalar(select(func.count()).select_from(Experiment).where(Experiment.run_id.in_(visible(Run,'run').with_only_columns(Run.id))))
        return {'projects':[as_dict(x) for x in projects],'assets':[as_dict(x,('path',)) for x in assets],'runs':[as_dict(x) for x in runs],
          'evaluations':[as_dict(x,('prediction_path',)) for x in evaluations],
          'counts':{'projects':len(projects),'assets':asset_count,'evaluations':evaluation_count,'experiments':experiment_count},'capabilities':capabilities()}

def create_creative(body: CreativeCreate) -> dict:
    with Session() as db: asset=db.get(Asset,body.asset_id)
    if asset is None or asset.kind not in {'image','video'}: raise DomainError('Select an image or video asset')
    destination=settings().data/'renders'/f'{uid()}.mp4'
    spec=body.model_dump()
    compose(Path(asset.path),destination,spec)
    return register_asset(destination,f'{body.headline[:65]} — composition','video',{'composition':spec,'source_asset_id':asset.id,'audio_note':'Composition is silent; original source is preserved.'})
