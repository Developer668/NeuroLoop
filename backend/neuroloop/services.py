"""Shared domain services used by HTTP, MCP and the run worker."""
from __future__ import annotations
import json, os
from pathlib import Path
from sqlalchemy import select, func
from .config import settings
from .db import Session, Asset, Project, Run, Evaluation, Experiment, RunEvent, ArchivedRecord, as_dict, uid, now
from .schemas import ProjectCreate, RunCreate, CreativeCreate
from .media import inspect_media, thumbnail, digest, compose, SUFFIXES

class DomainError(ValueError):
    pass

def capabilities() -> dict:
    s=settings(); root=s.root
    assets=[('TRIBE brain weights',root/'tribev2-balanced-qv-local/best.ckpt'),('INT8 video encoder',root/'tribev2-balanced-qv-local/quantized_video/model.safetensors'),('NF4 text encoder',root/'models/text/llama-3.2-3b-unsloth-q4/model.safetensors'),('Audio encoder',root/'models/audio/w2v-bert-2.0/model.safetensors')]
    with Session() as db:
        latest=db.scalar(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(1))
        verification={'evaluation_id':latest.id,'profile':latest.profile,'created_at':latest.created_at} if latest else None
    from .execution_guard import execution_status
    return {'product':'NeuroLoop','version':'0.1.0','execution':execution_status(),'deployment':'single-workspace authenticated local service','training':False,'models':[{'name':name,'status':'downloaded' if path.is_file() else 'missing'} for name,path in assets],
      'tribe':{'status':'weights_present' if all(p.is_file() for _,p in assets) else 'missing_weights','last_technical_test':verification,'meaning':'Predicted average-subject cortical response; not thoughts or purchase intent.'},
      'tsam':{'status':'experimental_weights_present' if (root/'models/emotion/tsam/weights/tsam_weights.tar').is_file() else 'missing_weights','reason':'Weight presence is checked now; loading is checked during an explicitly requested CPU evaluation. Experimental uncalibrated logits; excluded from optimization scoring.'},
      'kragel':{'status':'blocked','reason':'32,492 versus 10,242 vertices per hemisphere. Spatial registration and synthetic-signal interpretation have not been validated.'},
      'modalities':{'video':'neural analysis and bounded controlled edits','image':'explicit experimental repeated-frame presentation','audio':'audio response; local speech transcription or supplied timed words','text':'requires explicit timed-word transcript'},
      'asr':{'status':'available' if (root/'models/preprocessing/faster-whisper-small/model.bin').exists() else 'not_installed','purpose':'Speech preprocessing only; not another content judge.'},
      'integrations':[
        {'name':'Weights & Biases Weave','status':'configured' if s.weave_enabled and bool(os.getenv('WANDB_API_KEY')) else 'not_configured','purpose':'Experiment trace and metric provenance'},
        {'name':'W&B Inference','status':'configured' if s.planner_enabled and bool(os.getenv('WANDB_API_KEY')) else 'not_configured','purpose':'Optional structured experiment planner'},
        {'name':'ARIA / W&B Launch','status':'check_live_connection','purpose':'Versioned, locally approved jobs; check the live agent and inspect each result receipt'},
        {'name':'CoreWeave','status':'local_gpu','purpose':'Laptop compute only; no tested cloud deployment'},
        {'name':'marimo','status':'check_live_connection','purpose':'Read-only recorded evidence. Check service connections for the current HTTP response'},
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

def update_project(identity: str,body: ProjectCreate) -> dict:
    with Session.begin() as db:
        item=db.get(Project,identity)
        if item is None: raise DomainError('Project not found')
        for asset_id in ([body.asset_id] if body.asset_id else [])+body.reference_ids:
            if not db.get(Asset,asset_id): raise DomainError('Asset not found')
        if body.asset_id in body.reference_ids: raise DomainError('Original and reference must differ')
        for key,value in body.model_dump().items(): setattr(item,key,value)
        return as_dict(item)

def create_run(body: RunCreate,key: str | None=None,expected_project:dict|None=None) -> dict:
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
        if body.mode in {'compare','optimize'} and not project.reference_ids:
            raise DomainError('Choose at least one reference for this objective')
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
        supported_constraints={'preserve_duration','preserve_audio','locked_copy','max_filter_edits'}
        if set(project.constraints)-supported_constraints:
            raise DomainError('Unsupported constraints: '+', '.join(sorted(set(project.constraints)-supported_constraints)))
        if project.constraints.get('locked_copy') and not original.details.get('composition'):
            raise DomainError('Exact-copy locking requires an editable composition with a known text layer')
        if type(project.constraints.get('max_filter_edits',2)) is not int or not 0<=project.constraints.get('max_filter_edits',2)<=4:
            raise DomainError('max_filter_edits must be an integer between 0 and 4')
        for field in ['preserve_duration','preserve_audio']:
            if field in project.constraints and not isinstance(project.constraints[field],bool):
                raise DomainError(field+' must be boolean')
        required=1+len(project.reference_ids)
        if body.max_evaluations<required:
            raise DomainError(f'The baseline and references require a budget of at least {required} evaluations')
        for ref_id in project.reference_ids:
            ref=db.get(Asset,ref_id)
            if not ref: raise DomainError('Reference asset no longer exists')
            if ref.sha256==original.sha256: raise DomainError('A reference cannot be a duplicate of the original')
            if ref.kind != original.kind:
                raise DomainError('Reference and original must use the same source modality for this comparison')
            if ref.kind=='text':
                raise DomainError('Cross-document timed-text comparison needs per-document timing; analyze documents individually first')
        asr_ready=(settings().root/'models/preprocessing/faster-whisper-small/model.bin').is_file()
        for media_id in [original.id]+project.reference_ids:
            selected=db.get(Asset,media_id)
            words=(body.transcript or selected.details.get('transcript',[])) if media_id==original.id else selected.details.get('transcript',[])
            if selected.details.get('has_audio') and not body.no_speech and not words and not asr_ready:
                raise DomainError('Speech preprocessing is unavailable. Supply timed words for each spoken asset, or explicitly confirm all inputs contain no speech.')
        snapshots={media_id:dict(db.get(Asset,media_id).details) for media_id in [original.id]+project.reference_ids}
        config={'request':body.model_dump(),'project_snapshot':as_dict(project),'asset_metadata_snapshots':snapshots,'objective':'spatially-centered-cosine/eight-normalized-time-bins/v1'}
        run=Run(project_id=project.id,mode=body.mode,max_evaluations=body.max_evaluations,config=config,idempotency_key=key)
        db.add(run); db.flush(); db.add(RunEvent(run_id=run.id,kind='queued',message='Run queued with a fixed objective and evaluation budget.',details={'budget':body.max_evaluations}))
        return as_dict(run)

def get_run(identity: str) -> dict:
    with Session() as db:
        row=db.get(Run,identity)
        if not row: raise DomainError('Run not found')
        result=as_dict(row)
        result['experiments']=[as_dict(x) for x in db.scalars(select(Experiment).where(Experiment.run_id==identity).order_by(Experiment.sequence))]
        result['events']=[as_dict(x) for x in db.scalars(select(RunEvent).where(RunEvent.run_id==identity).order_by(RunEvent.id))]
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
