"""Durable single-GPU executor with checkpoints, cache, bounded search and recovery."""
from __future__ import annotations
import hashlib, json, logging, math, os, threading, time, subprocess, sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from filelock import FileLock,Timeout
from sqlalchemy import select
from .config import settings
from .db import Session,Asset,Run,Evaluation,Experiment,initialize,now,uid,emit
from . import inference,media,policy
from .readout import compare_references,METRIC
from .response import target_score as response_target_score
from .services import register_asset
from .integrations import planner_proposal,record_evidence
from .strategy import CreativeStrategist,InterventionProposal,operator_implementation
from .telemetry import traced

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
    return np.load(item.prediction_path,allow_pickle=False,mmap_mode='r')

def render_candidate(run_id: str,original: Asset,best: Asset,best_eval: Evaluation,operator: str | InterventionProposal,experiment_id: str) -> Asset:
    if isinstance(operator,InterventionProposal):
        proposal=operator
        operator=proposal.operator
    else:
        operator=str(operator)
    implementation=operator_implementation(operator)
    stage(run_id,'Rendering a controlled counterfactual')
    destination=settings().data/'renders'/f'{experiment_id}.mp4'
    config=dict(best.details.get('composition') or {})
    chain=list(best.details.get('edit_chain') or [])
    with Session() as db:
        locked=db.get(Run,run_id).config['project_snapshot']['constraints']
    if implementation.renderer=='ffmpeg_filter' and len(chain)>=int(locked.get('max_filter_edits',2)):
        raise ValueError('Bounded filter-edit limit reached; refusing cumulative proxy exploitation')
    if config:
        if implementation.renderer=='composition_timing':
            delta=float(implementation.delta_seconds or 0)
            config['headline_start']=max(0,min(config['duration']-0.5,config['headline_start']+delta))
            if config['headline_start']==best.details['composition']['headline_start']: raise ValueError('Timing edit has no valid change remaining')
        else: chain.append(operator)
        source=get_asset(config['asset_id'])
        render_target=destination if not chain else destination.with_name(destination.stem+'-base.mp4')
        media.compose(Path(source.path),render_target,config)
        source_path=render_target
    else:
        if implementation.renderer=='composition_timing': raise ValueError('Headline timing requires an editable composition; a flattened video has no independent text layer')
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


def _proposal_from_experiment(
    experiment: Experiment,
    strategist: CreativeStrategist,
    target: dict | None,
    response_report: dict | None,
    timeline: dict,
    prior: list[Experiment],
    constraints: dict,
) -> InterventionProposal:
    """Load a typed pending proposal, with a compatibility path for old rows."""

    specification = experiment.specification if isinstance(experiment.specification,dict) else {}
    try:
        return InterventionProposal.model_validate({key:value for key,value in specification.items() if key not in {'lineage','parent_id','sibling_ids','siblings'}})
    except Exception:
        # Rows written before the typed contract can still be resumed, but the
        # worker reconstructs them through the deterministic local backend.
        proposal = strategist.propose(
            target,
            response_report,
            timeline,
            prior,
            constraints,
            allowed_operators=[experiment.operator],
            seed=experiment.id,
            lineage_id=str(specification.get("lineage_id") or f"legacy:{experiment.id}"),
            parent_experiment_id=specification.get("parent_experiment_id"),
        )
        if proposal is None:
            raise StopRun("Saved intervention proposal is no longer permitted")
        if experiment.hypothesis and experiment.hypothesis != proposal.hypothesis:
            proposal = proposal.model_copy(update={"hypothesis": experiment.hypothesis})
        return proposal


def _create_experiment_batch(
    run_id: str,
    proposals: list[InterventionProposal],
    baseline_score: float,
    sequence: int,
) -> tuple[list[Experiment], int]:
    """Persist one A/B/C sibling group before any candidate is rendered."""

    rows: list[Experiment] = []
    next_sequence = sequence
    for proposal in proposals:
        next_sequence += 1
        rows.append(
            Experiment(
                id=uid(),
                run_id=run_id,
                sequence=next_sequence,
                operator=proposal.operator,
                hypothesis=proposal.hypothesis,
                specification=proposal.as_dict(),
                baseline_score=baseline_score,
            )
        )
    sibling_ids = [row.id for row in rows]
    with Session.begin() as db:
        db.add_all(rows)
        db.flush()
        for row, proposal in zip(rows, proposals):
            specification = dict(row.specification)
            specification.update(
                {
                    "lineage_id": proposal.lineage_id,
                    "lineage": proposal.lineage_id,
                    "parent_experiment_id": proposal.parent_experiment_id,
                    "parent_id": proposal.parent_experiment_id,
                    "sibling_ids": sibling_ids,
                    "siblings": sibling_ids,
                    "branch": proposal.branch,
                }
            )
            row.specification = specification
    return rows, next_sequence


def _mark_invalid_experiment(identity: str, experiment_id: str, reason: str, error_type: str) -> None:
    with Session.begin() as db:
        row = db.get(Experiment, experiment_id)
        if row:
            row.decision = "invalid"
            row.evidence = {
                "valid": False,
                "reason": reason,
                "exception_type": error_type,
                "policy_update": "omitted_invalid_candidate",
            }
    emit(
        identity,
        "rejected_invalid",
        "Candidate was not scoreable; the previous best and contextual policy were preserved.",
        experiment_id=experiment_id,
        reason=reason,
        exception_type=error_type,
    )


def _timeline_for_evaluation(evaluation_item: Evaluation) -> dict:
    evidence = evaluation_item.evidence or {}
    return {
        "source_duration": evidence.get("source_duration"),
        "times": evidence.get("times") or [],
        "segment_durations": evidence.get("segment_durations") or [],
        "time_axis": (evidence.get("response_ensemble") or {}).get("time_axis"),
    }

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
    best=original; best_eval=baseline; best_score=float(baseline_metric['value']); best_experiment_id=None
    baseline_report=baseline.evidence.get('response_ensemble')
    timeline=_timeline_for_evaluation(baseline)
    context_data={
        'metric':metric_name,
        'min_gain':config['min_gain'],
        'operators':sorted(config['operators']),
        'profile':baseline.profile,
        'reference_hashes':[get_asset(x).sha256 for x in active_reference_ids],
        'target':config.get('target'),
        'response_report':baseline_report,
        'timeline':timeline,
        'kind':original.kind,
        'constraints':project['constraints'],
        'brief':project['brief'],
    }
    context=policy.context_id(context_data)
    with Session() as db:
        prior=db.scalars(select(Experiment).where(Experiment.run_id==identity).order_by(Experiment.sequence)).all()
    sequence=max([x.sequence for x in prior],default=0)
    rejections=0
    lineage_decisions: dict[str, list[str]] = {}
    for row in prior:
        if row.decision=='kept' and row.asset_id and row.candidate_score is not None:
            if float(row.candidate_score)>=best_score:
                candidate_asset=get_asset(row.asset_id)
                with Session() as db: best_eval=db.get(Evaluation,row.evidence.get('evaluation_id'))
                if best_eval is not None:
                    best=candidate_asset
                    best_score=float(row.candidate_score);best_experiment_id=row.id
        if row.decision in {'kept','invalid','reverted','tradeoff'}:
            specification=row.specification if isinstance(row.specification,dict) else {}
            lineage=str(specification.get('lineage_id') or f'legacy:{row.id}')
            lineage_decisions.setdefault(lineage,[]).append(row.decision)
    for decisions in lineage_decisions.values():
        rejections=0 if 'kept' in decisions else rejections+1
    result['best_asset_id']=best.id;result['best_evaluation_id']=best_eval.id
    if best.id!=original.id:
        result['best_metric']=measured_metric(best_eval)
        if best_eval.evidence.get('response_ensemble'): result['best_response']=best_eval.evidence['response_ensemble']
    result['policy_context']=context
    result['strategy_backend']=CreativeStrategist.backend_identity
    set_result(identity,result)
    allowed=list(config['operators'])
    if not original.details.get('composition'): allowed=[x for x in allowed if not x.startswith('headline_')]
    strategist=CreativeStrategist()
    current_report=best_eval.evidence.get('response_ensemble') if best_eval else baseline_report
    while True:
        run=checkpoint(identity)
        if best_score>=config['target_score']: raise StopRun('Declared response target reached' if response_objective else 'Declared reference target reached')
        remaining=run.max_evaluations-run.evaluations_used
        if remaining<=0: raise StopRun('Evaluation budget exhausted; retained best validated candidate')
        if rejections>=2:
            emit(identity,'meta_stop','Plateau detected under the fixed acceptance contract. No more renders are justified.',consecutive_rejections=rejections,policy='bounded-plateau/v1')
            raise StopRun('Two consecutive edits failed the minimum gain; stopped rather than generating indefinitely')

        pending=[row for row in prior if row.decision=='proposed']
        if pending:
            # Resume one saved sibling lineage at a time.  An interrupted run
            # can therefore finish its already-reserved branch without making
            # a new proposal or changing the immutable parent.
            lineage=(pending[0].specification or {}).get('lineage_id') if isinstance(pending[0].specification,dict) else None
            pending=[row for row in pending if ((row.specification or {}).get('lineage_id') if isinstance(row.specification,dict) else None)==lineage]
            batch_rows=pending[:min(3,int(remaining))]
            proposals=[_proposal_from_experiment(row,strategist,config.get('target') if response_objective else None,current_report,timeline,prior,project['constraints']) for row in batch_rows]
            emit(identity,'resumed_experiment','Resuming the saved sibling lineage; saved renders and evaluations are reused.',lineage_id=lineage,sibling_count=len(batch_rows))
        else:
            branch_limit=min(policy.MAX_BRANCHES,int(remaining))
            choices=policy.choose_batch(context,allowed,{row.operator for row in prior},f'{identity}:{sequence}',limit=branch_limit)
            if not choices: raise StopRun('No untested permitted operators remain')
            policy_operators=[choice['operator'] for choice in choices]
            proposals=strategist.propose_candidates(
                config.get('target') if response_objective else None,
                current_report,
                timeline,
                prior,
                project['constraints'],
                allowed_operators=policy_operators,
                max_candidates=branch_limit,
                seed=f'{identity}:{sequence}',
                lineage_id=f'{identity}:lineage:{sequence+1}',
                parent_experiment_id=best_experiment_id,
            )
            if not proposals: raise StopRun('No deterministic intervention proposals remain')
            batch_rows,sequence=_create_experiment_batch(identity,proposals,best_score,sequence)
            prior.extend(batch_rows)
            for choice,proposal,row in zip(choices,proposals,batch_rows):
                emit(identity,'hypothesis',proposal.hypothesis,operator=proposal.operator,experiment_id=row.id,lineage_id=proposal.lineage_id,branch=proposal.branch,policy=choice['source'])

        outcomes=[]
        for row,proposal in zip(batch_rows,proposals):
            beginning=time.monotonic()
            try:
                candidate=get_asset(row.asset_id) if row.asset_id else render_candidate(identity,original,best,best_eval,proposal,row.id)
                with Session.begin() as db:
                    saved=db.get(Experiment,row.id)
                    if saved: saved.asset_id=candidate.id
                candidate_eval=evaluation(identity,candidate,config)
                if candidate_eval.profile!=baseline.profile:
                    raise RuntimeError('Evaluator changed during the run; refusing mixed-profile comparison')
                metric=measured_metric(candidate_eval)
                if not metric or not math.isfinite(float(metric.get('value'))):
                    raise ValueError('Candidate did not produce finite scoreable objective evidence')
                gain=float(metric['value'])-best_score
                worst_delta=None
                if not response_objective:
                    old=measured_metric(best_eval)
                    if not old or not old.get('per_reference') or not metric.get('per_reference'):
                        raise ValueError('Candidate/reference evidence is incomplete')
                    worst_delta=min(a['value']-b['value'] for a,b in zip(metric['per_reference'],old['per_reference']))
                outcomes.append({'row':row,'proposal':proposal,'candidate':candidate,'evaluation':candidate_eval,'metric':metric,'gain':gain,'worst_delta':worst_delta,'seconds':time.monotonic()-beginning,'valid':True})
            except StopRun:
                raise
            except Exception as exc:
                if isinstance(exc,RuntimeError) and str(exc).startswith('Evaluator changed during the run'):
                    raise
                _mark_invalid_experiment(identity,row.id,str(exc),type(exc).__name__)
                outcomes.append({'row':row,'proposal':proposal,'valid':False,'seconds':time.monotonic()-beginning,'error':str(exc)})

        valid=[outcome for outcome in outcomes if outcome['valid']]
        eligible=[outcome for outcome in valid if outcome['gain']>=config['min_gain'] and not (outcome['worst_delta'] is not None and outcome['worst_delta'] < -config['min_gain'])]
        winner=max(eligible,key=lambda outcome: (outcome['metric']['value'],outcome['proposal'].branch),default=None)
        for outcome in valid:
            outcome['decision']='kept' if winner is outcome else ('tradeoff' if outcome['worst_delta'] is not None and outcome['worst_delta'] < -config['min_gain'] else 'reverted')
            row=outcome['row'];candidate_eval=outcome['evaluation'];metric=outcome['metric'];gain=outcome['gain']
            evidence={'valid':True,'evaluation_id':candidate_eval.id,'metric':metric,'gain':gain,'worst_reference_delta':outcome['worst_delta'],'constraint_checks':{'duration_preserved':True},'reference_tradeoff':outcome['decision']=='tradeoff','selection':'winner' if winner is outcome else 'rejected_sibling','lineage_id':outcome['proposal'].lineage_id,'lineage':outcome['proposal'].lineage_id,'sibling_ids':(row.specification or {}).get('sibling_ids',[]),'siblings':(row.specification or {}).get('sibling_ids',[]),'response_ensemble':candidate_eval.evidence.get('response_ensemble')}
            with Session.begin() as db:
                saved=db.get(Experiment,row.id)
                saved.candidate_score=float(metric['value']);saved.decision=outcome['decision'];saved.evidence=evidence
                policy.record_valid_in_session(db,context,outcome['proposal'].operator,gain,outcome['seconds'],config['min_gain'],decision=outcome['decision'],valid=True)
            emit(identity,outcome['decision'],'Accepted the best measured sibling.' if winner is outcome else 'Retained the previous candidate; this valid sibling was not the batch winner.',experiment_id=row.id,lineage_id=outcome['proposal'].lineage_id,branch=outcome['proposal'].branch,gain=gain)
            record_evidence(identity,row.id,{'gain':gain,'decision':outcome['decision'],'metric':metric_name,'evaluation_id':candidate_eval.id,'lineage_id':outcome['proposal'].lineage_id})

        if winner is not None:
            best=winner['candidate'];best_eval=winner['evaluation'];best_score=float(winner['metric']['value']);best_experiment_id=winner['row'].id;rejections=0
            current_report=best_eval.evidence.get('response_ensemble') or current_report
            result.update(best_asset_id=best.id,best_evaluation_id=best_eval.id,best_metric=winner['metric'])
            if best_eval.evidence.get('response_ensemble'): result['best_response']=best_eval.evidence['response_ensemble']
        else:
            rejections+=1
        result['experiments_completed']=sequence;result['last_lineage_id']=proposals[0].lineage_id if proposals else None;set_result(identity,result)
        with Session() as db:
            prior=db.scalars(select(Experiment).where(Experiment.run_id==identity).order_by(Experiment.sequence)).all()


def heartbeat(identity: str,done: threading.Event) -> None:
    while not done.wait(5):
        with Session.begin() as db:
            row=db.get(Run,identity)
            if row and row.status=='running': row.heartbeat=now()

def process(identity: str) -> None:
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
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL)
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
                job.close()
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(timeout=5)
                finish_interrupted(identity,
                    pressure or ('Cancelled; completed evidence preserved' if cancelled else 'Run time limit reached; completed evidence preserved'),
                    cancelled=cancelled)
                return
            time.sleep(0.5)
        finish_interrupted(identity, f'Run process exited before completion (exit {child.returncode}); completed evidence preserved')
    finally:
        job.close()
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)


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
