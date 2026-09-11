"""Transactional recovery changes. Refuse unexpected source rather than overwrite it."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT/'data/build-backups/recovery'
def patch(file,old,new):
 p=ROOT/file;text=p.read_text(encoding='utf8')
 if new in text:return
 if text.count(old)!=1:raise RuntimeError('Unexpected source: '+file+' '+old[:60])
 backup=BACKUP/file;backup.parent.mkdir(parents=True,exist_ok=True)
 if not backup.exists():shutil.copy2(p,backup)
 tmp=p.with_name(p.name+'.recovery-new');tmp.write_text(text.replace(old,new),encoding='utf8');tmp.replace(p);print(file)
patch('backend/neuroloop/policy.py',"def record(context: str,operator: str,gain: float,seconds: float,threshold: float) -> None:\n    with Session.begin() as db:\n        key=f'{context}:{operator}'; row=db.get(PolicyStat,key)\n        if row is None:\n            row=PolicyStat(key=key,context=context,operator=operator,successes=0,failures=0,total_gain=0,total_seconds=0);db.add(row)\n        row.successes+=int(gain>=threshold);row.failures+=int(gain<threshold)\n        row.total_gain+=gain;row.total_seconds+=seconds;row.updated_at=now()", "def record_in_session(db, context: str,operator: str,gain: float,seconds: float,threshold: float) -> None:\n    key=f'{context}:{operator}'; row=db.get(PolicyStat,key)\n    if row is None:\n        row=PolicyStat(key=key,context=context,operator=operator,successes=0,failures=0,total_gain=0,total_seconds=0);db.add(row)\n    row.successes+=int(gain>=threshold);row.failures+=int(gain<threshold)\n    row.total_gain+=gain;row.total_seconds+=seconds;row.updated_at=now()\n\ndef record(context: str,operator: str,gain: float,seconds: float,threshold: float) -> None:\n    with Session.begin() as db:\n        record_in_session(db,context,operator,gain,seconds,threshold)")
patch('backend/neuroloop/services.py',"config={'request':body.model_dump(),'project_snapshot':as_dict(project),'objective':'spatially-centered-cosine/eight-normalized-time-bins/v1'}", "snapshots={media_id:dict(db.get(Asset,media_id).details) for media_id in [original.id]+project.reference_ids}\n        config={'request':body.model_dump(),'project_snapshot':as_dict(project),'asset_metadata_snapshots':snapshots,'objective':'spatially-centered-cosine/eight-normalized-time-bins/v1'}")
patch('backend/neuroloop/services.py',"not isinstance(project.constraints.get('max_filter_edits',2),int)","type(project.constraints.get('max_filter_edits',2)) is not int")
patch('backend/neuroloop/worker.py',"    original=get_asset(project['asset_id'])\n", "    original=get_asset(project['asset_id'])\n    snapshots=run.config.get('asset_metadata_snapshots',{})\n    if original.id in snapshots: original.details=snapshots[original.id]\n    config={**config,'transcript':config.get('transcript') or original.details.get('transcript',[])}\n")
patch('backend/neuroloop/worker.py',"        ref=get_asset(ref_id);ref_config={**config,'transcript':ref.details.get('transcript',[])}", "        ref=get_asset(ref_id)\n        if ref.id in snapshots: ref.details=snapshots[ref.id]\n        ref_config={**config,'transcript':ref.details.get('transcript',[])}")
patch('backend/neuroloop/worker.py',"    excluded={x.operator for x in prior};sequence=len(prior);rejections=0", "    excluded={x.operator for x in prior};sequence=max([x.sequence for x in prior],default=0);rejections=0\n    pending=[x for x in prior if x.decision=='proposed']\n    for x in prior:\n        if x.decision=='kept': rejections=0\n        elif x.decision in {'invalid','reverted','tradeoff'}: rejections+=1")
patch('backend/neuroloop/worker.py',"        if run.evaluations_used>=run.max_evaluations: raise StopRun('Evaluation budget exhausted; retained best validated candidate')", "        if run.evaluations_used>=run.max_evaluations and not pending: raise StopRun('Evaluation budget exhausted; retained best validated candidate')")
start="        proposal=policy.choose(context,allowed,excluded,f'{identity}:{sequence}')"
end="        beginning=time.monotonic()"
p=ROOT/'backend/neuroloop/worker.py';text=p.read_text(encoding='utf8');i=text.index(start);j=text.index(end,i)
old=text[i:j]
new="""        if pending:
            exp=pending.pop(0);operator=exp.operator;proposal=exp.specification
            emit(identity,'resumed_experiment','Resuming the same experiment; saved render and inference are reused.',experiment_id=exp.id)
        else:
            proposal=policy.choose(context,allowed,excluded,f'{identity}:{sequence}')
            if proposal is None: raise StopRun('No untested permitted operators remain')
            if sequence==0:
                try:
                    suggested=planner_proposal(project['brief'],[x for x in allowed if x not in excluded],{'baseline_metric':baseline_metric,'remaining_evaluations':run.max_evaluations-run.evaluations_used})
                    if suggested: proposal.update(suggested);result['planner']=suggested['source']
                except Exception as exc:
                    emit(identity,'planner_unavailable','Planner unavailable; using the disclosed adaptive search policy.',error=type(exc).__name__)
            operator=proposal['operator'];excluded.add(operator);sequence+=1
            exp=Experiment(id=uid(),run_id=identity,sequence=sequence,operator=operator,hypothesis=proposal['hypothesis'],specification=proposal,baseline_score=best_score)
            with Session.begin() as db: db.add(exp)
            emit(identity,'hypothesis',proposal['hypothesis'],operator=operator,experiment_id=exp.id,policy=proposal['source'])
"""
patch('backend/neuroloop/worker.py',old,new)
patch('backend/neuroloop/worker.py',"            candidate=render_candidate(identity,original,best,best_eval,operator,exp.id)", "            candidate=get_asset(exp.asset_id) if exp.asset_id else render_candidate(identity,original,best,best_eval,operator,exp.id)")
patch('backend/neuroloop/worker.py',"        policy.record(context,operator,gain if keep else min(gain,0.0),time.monotonic()-beginning,config['min_gain'])", "            policy.record_in_session(db,context,operator,gain if keep else min(gain,0.0),time.monotonic()-beginning,config['min_gain'])")
patch('backend/neuroloop/inference.py',"from pathlib import Path", "from pathlib import Path\nfrom functools import lru_cache\nfrom .persistence import atomic_json, atomic_numpy")
patch('backend/neuroloop/inference.py',"def profile_id() -> str:", "@lru_cache(maxsize=1)\ndef profile_id() -> str:")
patch('backend/neuroloop/inference.py',"    np.save(output/'prediction.npy',predictions,allow_pickle=False)", "    atomic_numpy(output/'prediction.npy',predictions)")
patch('backend/neuroloop/inference.py',"    (output/'segments.json').write_text(json.dumps([{'start':float(x.start),'duration':float(x.duration)} for x in segments]),encoding='utf8')", "    atomic_json(output/'segments.json',[{'start':float(x.start),'duration':float(x.duration)} for x in segments])")
patch('backend/neuroloop/inference.py',"    (output/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')", "    atomic_json(output/'evidence.json',evidence)")
print('Recovery hardening complete.')
