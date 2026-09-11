"""Fixed Launch entrypoint: consume one locally approved proposal and mirror results."""
from pathlib import Path
import os,sys,time,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.agent_bridge import get_proposal,execute
from neuroloop import services
from neuroloop.persistence import atomic_json
import wandb

def main():
    identity=os.environ['NEUROLOOP_APPROVED_PROPOSAL']
    proposal=get_proposal(identity)
    if proposal['status'] not in {'approved','queued'}:raise ValueError('Proposal has not been approved locally')
    remote=wandb.init(settings=wandb.Settings(disable_git=True,disable_code=True,disable_job_creation=True,x_disable_stats=True,console='off'))
    run=execute(identity,proposal['approval_digest'])
    target=ROOT/'data/verification/release';target.mkdir(parents=True,exist_ok=True)
    receipt={'version':1,'proposal_id':identity,'local_run_id':run['id'],'wandb_run_id':remote.id,'url':remote.url,'status':'running'}
    destination=target/('launch-'+identity+'.json')
    atomic_json(destination,receipt)
    try:
        deadline=time.monotonic()+960
        while time.monotonic()<deadline:
            run=services.get_run(run['id'])
            if run['status'] not in {'queued','running'}:break
            time.sleep(3)
        else:
            services.cancel_run(run['id']);raise TimeoutError('Bounded Launch wait expired; cancellation requested')
        remote.summary.update({'local_run_id':run['id'],'local_status':run['status'],'evaluations_used':run['evaluations_used'],'compute_seconds':run['compute_seconds'],'contract_version':1,'proposal_id':identity})
        for exp in run['experiments']:
            if exp['candidate_score'] is not None:
                remote.log({'sequence':exp['sequence'],'operator':exp['operator'],'baseline_score':exp['baseline_score'],'candidate_score':exp['candidate_score'],'gain':exp['candidate_score']-exp['baseline_score'],'decision':exp['decision']})
        receipt.update(status=run['status'],result=run['result'],evaluations_used=run['evaluations_used'],compute_seconds=run['compute_seconds'],remote_status='awaiting_readback')
        atomic_json(destination,receipt)
        remote.finish(exit_code=0 if run['status']=='completed' else 1)
        recorded=wandb.Api().run(f'{remote.entity}/{remote.project}/{remote.id}')
        if recorded.summary.get('local_run_id')!=run['id'] or recorded.summary.get('local_status')!=run['status']:
            raise RuntimeError('Remote summary did not confirm the local result')
        receipt['remote_status']='confirmed';atomic_json(destination,receipt)
        if run['status']!='completed':raise RuntimeError(run.get('error') or run['status'])
    except BaseException as exc:
        services.cancel_run(run['id']);remote.finish(exit_code=1)
        receipt.update(error=type(exc).__name__)
        atomic_json(destination,receipt);raise

if __name__=='__main__':main()
