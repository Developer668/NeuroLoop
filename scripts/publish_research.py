"""Publish selected real local run metadata for ARIA; never publish source media/code."""
from pathlib import Path
import sys,os,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.db import Session,Run,Experiment,as_dict,initialize
from sqlalchemy import select
import wandb

def publish(limit=10):
    initialize();project=os.environ['WANDB_PROJECT'];entity,name=project.split('/',1)
    os.environ['WANDB_PROJECT']=name
    os.environ['WANDB_ENTITY']=entity
    target=ROOT/'data/verification/release';target.mkdir(parents=True,exist_ok=True)
    destination=target/'wandb-runs.json'
    output=json.loads(destination.read_text(encoding='utf8')) if destination.is_file() else []
    published={r['local_run_id'] for r in output}
    with Session() as db:
        runs=db.scalars(select(Run).where(Run.status.in_(['completed','failed'])).order_by(Run.created_at.desc()).limit(limit)).all()
        for row in runs:
            if row.id in published:continue
            request=row.config.get('request',{})
            experiments=db.scalars(select(Experiment).where(Experiment.run_id==row.id).order_by(Experiment.sequence)).all()
            remote=wandb.init(entity=entity,project=name,id='local-'+row.id.replace('-',''),name='Local '+row.mode+' / '+row.id[:8],resume='allow',job_type='local-research-metadata',dir=str(ROOT/'data'),config={'contract_version':1,'local_run_id':row.id,'mode':row.mode,'objective':row.config.get('objective'),'allowed_operators':request.get('operators',[]),'max_evaluations':row.max_evaluations,'max_seconds':request.get('max_seconds'),'min_gain':request.get('min_gain'),'local_created_at':row.created_at,'data_policy':'metadata-only','scientific_validation':'not established'},settings=wandb.Settings(disable_git=True,disable_code=True,disable_job_creation=True,x_disable_stats=True,console='off'))
            remote.summary.update({'local_status':row.status,'evaluations_used':row.evaluations_used,'compute_seconds':row.compute_seconds,'local_run_id':row.id,'experiment_count':len(experiments)})
            for exp in experiments:
                if exp.baseline_score is not None and exp.candidate_score is not None:
                    remote.log({'sequence':exp.sequence,'operator':exp.operator,'baseline_score':exp.baseline_score,'candidate_score':exp.candidate_score,'gain':exp.candidate_score-exp.baseline_score,'decision':exp.decision})
            url=remote.url;remote.finish(exit_code=0)
            # W&B status reflects completion of metadata publication. Original outcome is local_status.
            output.append({'local_run_id':row.id,'url':url,'local_status':row.status,'kind':'metadata-publication'})
            from neuroloop.persistence import atomic_json
            atomic_json(destination,output)
    return output
if __name__=='__main__':print(json.dumps(publish(),indent=2))
