"""Durable single-GPU executor with checkpoints, cache, bounded search and recovery."""
from __future__ import annotations
import hashlib, json, logging, os, threading, time, traceback, subprocess, sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
from filelock import FileLock,Timeout
from sqlalchemy import select,update
from .config import settings
from .db import Session,Asset,Run,Evaluation,Experiment,RunEvent,initialize,now,uid,emit
from . import inference,media,policy
from .readout import compare_references,METRIC
from .response import target_score as response_target_score
from .services import register_asset
from .integrations import planner_proposal,record_evidence
from .telemetry import traced
from .persistence import close_mmap

log=logging.getLogger(__name__)

class StopRun(Exception):
    pass

class CancelRun(Exception):
    pass

def checkpoint(identity: str,stage: str | None=None) -> Run:
    with Session.begin() as db:
        run=db.get(Run,identity)
        if not run: raise StopRun('Run no longer exists')
        if run.cancel_requested: raise CancelRun('Cancelled at a safe execution checkpoint')
        request=run.config['request']
        if run.started_at:
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(run.started_at)).total_seconds()
            if elapsed>=request['max_seconds']: raise StopRun('Wall-clock budget reached; in-flight work is preserved')
        if stage: run.stage=stage
        run.heartbeat=now()
        return run

def stage(identity: str,message: str) -> None:
    checkpoint(identity,message);emit(identity,'stage',message)

@traced('neuroloop.evaluate')
def evaluation(identity: str,asset: Asset,config: dict) -> Evaluation:
    run=checkpoint(identity)
    profile=inference.profile_id()
    meaningful={k:config.get(k) for k in ['no_speech','transcript','allow_static_presentation','presentation_seconds','include_tsam','include_kragel']}
    meaningful['transcript']=config.get('transcript') or asset.details.get('transcript',[])
    meaningful['metric_schema']=METRIC
    key=hashlib.sha256(json.dumps({'asset':asset.sha256,'profile':profile,'preprocessing':meaningful},sort_keys=True).encode()).hexdigest()
    with Session() as db:
        cached=db.scalar(select(Evaluation).where(Evaluation.cache_key==key))
        if cached and cached.prediction_path and Path(cached.prediction_path).is_file():
            emit(identity,'cache_hit','Reused a version-matched neural evaluation.',asset_id=asset.id,evaluation_id=cached.id)
            return cached
    output=settings().data/'results'/key
    # A completed result file is a crash-safe checkpoint even if database commit was interrupted.
    existing=output/'evidence.json'
    if existing.is_file() and (output/'prediction.npy').is_file():
        evidence=json.loads(existing.read_text(encoding='utf8'))
        if evidence.get('profile')!=profile: raise RuntimeError('Checkpoint profile mismatch')
    else:
        with Session.begin() as db:
            current=db.get(Run,identity)
            if current.evaluations_used>=current.max_evaluations: raise StopRun('Evaluation budget exhausted')
            current.evaluations_used+=1
        emit(identity,'evaluation_reserved','Reserved one neural evaluation before GPU execution.',asset_id=asset.id)
        evidence=inference.evaluate(Path(asset.path),asset.kind,asset.details,config,output,lambda msg:stage(identity,msg))
    item=Evaluation(asset_id=asset.id,cache_key=key,evaluator='TRIBE v2',profile=profile,evidence=evidence,prediction_path=str(output/'prediction.npy'),duration_seconds=evidence['seconds'])
    with Session.begin() as db:
        prior=db.scalar(select(Evaluation).where(Evaluation.cache_key==key))
        if prior: return prior
        db.add(item);db.flush()
        current=db.get(Run,identity);current.compute_seconds+=evidence['seconds']
    emit(identity,'evaluated','Recorded real cortical predictions.',asset_id=asset.id,evaluation_id=item.id,shape=evidence['shape'],seconds=evidence['seconds'])
    return item

def get_asset(identity: str) -> Asset:
    with Session() as db:
        item=db.get(Asset,identity)
        if not item: raise ValueError('Referenced asset no longer exists')
        return item

def load_prediction(item: Evaluation) -> np.ndarray:
    # Result arrays are small compared with the neural models. Materialize a
    # bounded copy here so the worker never retains mmap file descriptors while
    # it keeps reference scores across candidate evaluations.
    mapped=np.load(item.prediction_path,allow_pickle=False,mmap_mode='r')
    try:
        # np.memmap.copy() preserves the memmap subclass on the bundled
        # NumPy runtime.  Force a plain, owning ndarray so later scoring does
        # not retain the backing file mapping or its descriptor.
        return np.array(mapped, copy=True, subok=False, order='C')
    finally:
        close_mmap(mapped)

def render_candidate(run_id: str,original: Asset,best: Asset,best_eval: Evaluation,operator: str,experiment_id: str) -> Asset:
    stage(run_id,'Rendering a controlled counterfactual')
    destination=settings().data/'renders'/f'{experiment_id}.mp4'
    config=dict(best.details.get('composition') or {})
    chain=list(best.details.get('edit_chain') or [])
    with Session() as db:
        locked=db.get(Run,run_id).config['project_snapshot']['constraints']
    if not operator.startswith('headline_') and len(chain)>=int(locked.get('max_filter_edits',2)):
        raise ValueError('Bounded filter-edit limit reached; refusing cumulative proxy exploitation')
    if config:
        if operator.startswith('headline_'):
            delta=-0.75 if operator=='headline_early' else 0.75
            config['headline_start']=max(0,min(config['duration']-0.5,config['headline_start']+delta))
            if config['headline_start']==best.details['composition']['headline_start']: raise ValueError('Timing edit has no valid change remaining')
        else: chain.append(operator)
        source=get_asset(config['asset_id'])
        render_target=destination if not chain else destination.with_name(destination.stem+'-base.mp4')
        media.compose(Path(source.path),render_target,config)
        source_path=render_target
    else:
        if operator.startswith('headline_'): raise ValueError('Headline timing requires an editable composition; a flattened video has no independent text layer')
        chain.append(operator)
        source_path=Path(original.path)
        if original.kind=='image':
            base=settings().data/'renders'/f'{original.id}-standardized.mp4'
            media.static_presentation(source_path,base,int(best_eval.evidence['source_duration']));source_path=base
    if chain:
        if any(x not in media.FILTERS for x in chain): raise ValueError('Invalid filter in controlled edit chain')
        filters=','.join(media.FILTERS[x] for x in chain)
        media.execute(['-y','-i',str(source_path),'-vf',filters,'-map','0:v:0','-map','0:a?','-c:v','libx264','-crf','18','-preset','fast','-c:a','aac','-pix_fmt','yuv420p',str(destination)])
    details=media.inspect_media(destination,'video')
    expected=original.details.get('duration') or best_eval.evidence['source_duration']
    if abs(details['duration']-expected)>0.2: raise ValueError('Rendered duration violated the locked-duration constraint')
    if original.details.get('has_audio') and locked.get('preserve_audio',True) and not details.get('has_audio'):
        raise ValueError('Rendered candidate dropped the locked audio stream')
    extra={'source_asset_id':original.id,'edit_chain':chain,'operator':operator,'duration_preserved':True}
    if config: extra['composition']=config
    registered=register_asset(destination,f'{original.name[:120]} · {operator}','video',extra)
    return get_asset(registered['id'])

def set_result(identity: str,result: dict) -> None:
    with Session.begin() as db: db.get(Run,identity).result=result

@traced('neuroloop.run')
def execute_run(identity: str) -> None:
    run=checkpoint(identity,'Preparing evaluation contract'); config=run.config['request']; project=run.config['project_snapshot']
    original=get_asset(project['asset_id'])
    snapshots=run.config.get('asset_metadata_snapshots',{})
    if original.id in snapshots: original.details=snapshots[original.id]
    config={**config,'transcript':config.get('transcript') or original.details.get('transcript',[])}
    response_objective=config.get('objective')=='response_target'
    active_reference_ids=[] if response_objective else list(project['reference_ids'])
    references=[]; ref_evaluations=[]
    for ref_id in active_reference_ids:
        ref=get_asset(ref_id)
        if ref.id in snapshots: ref.details=snapshots[ref.id]
        ref_config={**config,'transcript':ref.details.get('transcript',[])}
        item=evaluation(identity,ref,ref_config)
        references.append((ref_id,load_prediction(item)));ref_evaluations.append(item.id)
    baseline=evaluation(identity,original,config)

    def measured_metric(item: Evaluation) -> dict | None:
        if response_objective:
            report=item.evidence.get('response_ensemble')
            return response_target_score(report,config.get('target')) if report else None
        return compare_references(load_prediction(item),references) if references else None

    baseline_metric=measured_metric(baseline)
    metric_name='response-target-distance/v1' if response_objective else METRIC
    result={'baseline_asset_id':original.id,'best_asset_id':original.id,'baseline_evaluation_id':baseline.id,'best_evaluation_id':baseline.id,'reference_evaluation_ids':ref_evaluations,'baseline_metric':baseline_metric,'best_metric':baseline_metric,'metric':metric_name,'scope':'Experimental TSAM + Kragel response-target objective; relative model evidence, not measured human preference.' if response_objective else 'Fixed predicted-neural-reference objective; not human preference or conversion.','policy':'context-scoped cost-aware Thompson sampling','planner':'not used','generation_calls':0}
    if baseline.evidence.get('response_ensemble'):
        result['baseline_response']=baseline.evidence['response_ensemble'];result['best_response']=baseline.evidence['response_ensemble']
    set_result(identity,result)
    if run.mode!='optimize':
        raise StopRun('Analysis complete' if run.mode=='analyze' else 'Reference comparison complete')
    if not baseline_metric: raise ValueError('Optimization objective produced no scoreable evidence')
    best=original; best_eval=baseline; best_score=baseline_metric['value']
    context_data={'metric':metric_name,'min_gain':config['min_gain'],'operators':sorted(config['operators']),'profile':baseline.profile,'reference_hashes':[get_asset(x).sha256 for x in active_reference_ids],'target':config.get('target'),'kind':original.kind,'constraints':project['constraints'],'brief':project['brief']}
    context=hashlib.sha256(json.dumps(context_data,sort_keys=True).encode()).hexdigest()[:32]
    with Session() as db: prior=db.scalars(select(Experiment).where(Experiment.run_id==identity).order_by(Experiment.sequence)).all()
    excluded={x.operator for x in prior};sequence=max([x.sequence for x in prior],default=0);rejections=0
    pending=[x for x in prior if x.decision=='proposed']
    for x in prior:
        if x.decision=='kept': rejections=0
        elif x.decision in {'invalid','reverted','tradeoff'}: rejections+=1
    for previous in prior:
        if previous.decision=='kept' and previous.asset_id:
            best=get_asset(previous.asset_id)
            with Session() as db: best_eval=db.get(Evaluation,previous.evidence['evaluation_id'])
            best_score=previous.candidate_score
    result['best_asset_id']=best.id;result['best_evaluation_id']=best_eval.id
    if best.id!=original.id:
        result['best_metric']=measured_metric(best_eval)
        if best_eval.evidence.get('response_ensemble'): result['best_response']=best_eval.evidence['response_ensemble']
    set_result(identity,result)
    allowed=list(config['operators'])
    if not original.details.get('composition'): allowed=[x for x in allowed if not x.startswith('headline_')]
    while True:
        run=checkpoint(identity)
        if best_score>=config['target_score']: raise StopRun('Declared response target reached' if response_objective else 'Declared reference target reached')
        if run.evaluations_used>=run.max_evaluations and not pending: raise StopRun('Evaluation budget exhausted; retained best validated candidate')
        if rejections>=2:
            emit(identity,'meta_stop','Plateau detected under the fixed acceptance contract. No more renders are justified.',consecutive_rejections=rejections,policy='bounded-plateau/v1')
            raise StopRun('Two consecutive edits failed the minimum gain; stopped rather than generating indefinitely')
        if pending:
            exp=pending.pop(0);operator=exp.operator;proposal=exp.specification
            emit(identity,'resumed_experiment','Resuming the same experiment; saved render and inference are reused.',experiment_id=exp.id)
        else:
            proposal=policy.choose(context,allowed,excluded,f'{identity}:{sequence}')
            if proposal is None: raise StopRun('No untested permitted operators remain')
            if sequence==0:
                try:
                    suggested=planner_proposal(project['brief'],[x for x in allowed if x not in excluded],{'baseline_metric':baseline_metric,'response_target':config.get('target'),'remaining_evaluations':run.max_evaluations-run.evaluations_used})
                    if suggested: proposal.update(suggested);result['planner']=suggested['source']
                except Exception as exc:
                    emit(identity,'planner_unavailable','Planner unavailable; using the disclosed adaptive search policy.',error=type(exc).__name__)
            operator=proposal['operator'];excluded.add(operator);sequence+=1
            exp=Experiment(id=uid(),run_id=identity,sequence=sequence,operator=operator,hypothesis=proposal['hypothesis'],specification=proposal,baseline_score=best_score)
            with Session.begin() as db: db.add(exp)
            emit(identity,'hypothesis',proposal['hypothesis'],operator=operator,experiment_id=exp.id,policy=proposal['source'])
        beginning=time.monotonic()
        try:
            candidate=get_asset(exp.asset_id) if exp.asset_id else render_candidate(identity,original,best,best_eval,operator,exp.id)
        except (ValueError,media.MediaError) as exc:
            with Session.begin() as db:
                row=db.get(Experiment,exp.id);row.decision='invalid';row.evidence={'reason':str(exc)}
            emit(identity,'rejected_invalid','Counterfactual failed a rendering or contract check; no preference update was made.',reason=str(exc))
            rejections+=1;continue
        with Session.begin() as db: db.get(Experiment,exp.id).asset_id=candidate.id
        candidate_eval=evaluation(identity,candidate,config)
        if candidate_eval.profile!=baseline.profile: raise RuntimeError('Evaluator changed during the run; refusing mixed-profile comparison')
        metric=measured_metric(candidate_eval)
        if not metric: raise ValueError('Candidate did not produce scoreable objective evidence')
        gain=metric['value']-best_score
        keep=gain>=config['min_gain'];decision='kept' if keep else 'reverted';worst_delta=None
        if not response_objective:
            old=measured_metric(best_eval)
            worst_delta=min(a['value']-b['value'] for a,b in zip(metric['per_reference'],old['per_reference']))
            if worst_delta < -config['min_gain']: keep=False;decision='tradeoff'
        with Session.begin() as db:
            row=db.get(Experiment,exp.id);row.candidate_score=metric['value'];row.decision=decision
            row.evidence={'evaluation_id':candidate_eval.id,'metric':metric,'gain':gain,'worst_reference_delta':worst_delta,'constraint_checks':{'duration_preserved':True},'reference_tradeoff':decision=='tradeoff','response_ensemble':candidate_eval.evidence.get('response_ensemble')}
            policy.record_in_session(db,context,operator,gain if keep else min(gain,0.0),time.monotonic()-beginning,config['min_gain'])
        if keep:
            best=candidate;best_eval=candidate_eval;best_score=metric['value'];rejections=0
            result.update(best_asset_id=best.id,best_evaluation_id=best_eval.id,best_metric=metric)
            if candidate_eval.evidence.get('response_ensemble'): result['best_response']=candidate_eval.evidence['response_ensemble']
        else: rejections+=1
        result['experiments_completed']=sequence;set_result(identity,result)
        emit(identity,decision,'Accepted the measured improvement.' if keep else 'Retained the previous candidate; the fixed acceptance rule was not met.',experiment_id=exp.id,gain=gain)
        record_evidence(identity,exp.id,{'gain':gain,'decision':decision,'metric':metric_name,'evaluation_id':candidate_eval.id})


def heartbeat(identity: str,done: threading.Event) -> None:
    while not done.wait(5):
        with Session.begin() as db:
            row=db.get(Run,identity)
            if row and row.status=='running': row.heartbeat=now()

def process(identity: str) -> None:
    from .execution_guard import require_execution_enabled
    try:
        require_execution_enabled()
    except RuntimeError as exc:
        finish_interrupted(identity, str(exc))
        return
    done=threading.Event();thread=threading.Thread(target=heartbeat,args=(identity,done),daemon=True);thread.start()
    status='completed';reason='Completed';error=None
    try:
        execute_run(identity)
    except CancelRun as exc: status='cancelled';reason=str(exc)
    except StopRun as exc: reason=str(exc)
    except Exception as exc:
        status='failed';reason='Execution failed; no fabricated replacement result';error=f'{type(exc).__name__}: {exc}'
        log.exception('Run %s failed',identity)
    finally:
        done.set();thread.join(timeout=6)
        with Session.begin() as db:
            run=db.get(Run,identity);run.status=status;run.stage=reason;run.stop_reason=reason;run.error=error;run.finished_at=now();run.heartbeat=now()
        emit(identity,status,reason,error=error)

def finish_interrupted(identity: str, reason: str, cancelled: bool = False) -> None:
    with Session.begin() as db:
        row = db.get(Run, identity)
        if not row or row.status not in {'running', 'queued'}:
            return
        row.status = 'cancelled' if cancelled else 'failed'
        row.stage = reason
        row.stop_reason = reason
        row.error = None if cancelled else reason
        row.owner = None
        row.finished_at = now()
        row.heartbeat = now()
    emit(identity, 'cancelled' if cancelled else 'failed', reason)
    try:
        from .delivery import enqueue
        import uuid
        enqueue('neuroloop.interrupted',{'run_id':identity,'status':'cancelled' if cancelled else 'failed','started_at':row.started_at or row.created_at,'ended_at':row.finished_at,'evaluations_used':row.evaluations_used,'compute_seconds':row.compute_seconds},str(uuid.uuid5(uuid.NAMESPACE_URL,'neuroloop/interrupted/'+identity)))
    except Exception as exc:
        log.error('Could not persist interruption receipt: %s',type(exc).__name__)


def recover_interrupted_runs() -> None:
    # Called only while owning the exclusive worker lock. Never replay a job
    # that may have caused a driver/system crash merely by opening the app.
    with Session() as db:
        identities = list(db.scalars(select(Run.id).where(Run.status == 'running')))
    for identity in identities:
        finish_interrupted(identity, 'Worker interrupted; completed evidence preserved. Submit a new run to retry.')


def supervise_run(identity: str) -> None:
    """One child per run: bound execution, cancellation and resident model lifetime."""
    from .execution_guard import require_execution_enabled, pressure_reason, hold_execution
    from .hardware import hardware_status
    try:
        require_execution_enabled()
    except RuntimeError as exc:
        finish_interrupted(identity, str(exc))
        return
    with Session() as db:
        row = db.get(Run, identity)
        timeout = min(row.config['request']['max_seconds'], settings().model_timeout_seconds)
    command = [sys.executable, '-u', str(settings().root / 'scripts/run_worker.py'), '--run-id', identity]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from windows_job import OwnedJob
    job = OwnedJob()
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=os.name != 'nt')
    started = time.monotonic()
    last_telemetry = 0.0
    try:
        job.add(child)
        while child.poll() is None:
            pressure = None
            if time.monotonic() - last_telemetry >= 3:
                state = hardware_status()
                last_telemetry = time.monotonic()
                pressure = pressure_reason(state)
                if pressure:
                    hold_execution(pressure, identity, state)
            with Session() as db:
                row = db.get(Run, identity)
                cancelled = not row or bool(row.cancel_requested)
            if pressure or cancelled or time.monotonic() - started > timeout:
                job.terminate(child)
                finish_interrupted(identity,
                    pressure or ('Cancelled; completed evidence preserved' if cancelled else 'Run time limit reached; completed evidence preserved'),
                    cancelled=cancelled)
                return
            time.sleep(0.5)
        finish_interrupted(identity, f'Run process exited before completion (exit {child.returncode}); completed evidence preserved')
    finally:
        job.terminate(child)
        job.close()


def main() -> None:
    initialize();s=settings();owner=f'{os.getpid()}-{uid()}'
    from .execution_guard import require_execution_enabled, execution_status
    require_execution_enabled()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    lock=FileLock(s.data/'gpu-worker.lock')
    try:
        with lock.acquire(timeout=0):
            recover_interrupted_runs()
            log.info('NeuroLoop worker ready; one GPU executor, no synthetic fallback')
            while True:
                if execution_status()['paused']:
                    # Keep the owned service alive for review; never claim queued work.
                    # An intentional safety hold must not make the supervisor stop the API.
                    time.sleep(1)
                    continue
                with Session.begin() as db:
                    row=db.scalar(select(Run).where(Run.status=='queued').order_by(Run.created_at).limit(1))
                    identity=row.id if row else None
                    if row:
                        row.status='running';row.owner=owner;row.started_at=row.started_at or now();row.heartbeat=now()
                if identity: supervise_run(identity)
                else: time.sleep(0.75)
    except Timeout:
        raise SystemExit('Another NeuroLoop GPU worker already owns this data directory')

if __name__=='__main__': main()
