"""Reconcile the held run after a host crash, without resuming any execution."""
import json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.config import settings
from neuroloop.db import Session,Run,engine,initialize,now
from neuroloop.persistence import atomic_json
from sqlalchemy import text

def main():
    settings();initialize()
    hold=json.loads((ROOT/'data/inference-quarantine.json').read_text())
    identity=hold['interrupted_run_id']
    with Session.begin() as db:
        run=db.get(Run,identity)
        if run.status=='completed':raise RuntimeError('Refusing to reclassify a completed run')
        run.status='failed';run.stage='Host graphics crash; model execution paused. Completed evidence preserved.'
        run.stop_reason=run.stage;run.finished_at=run.finished_at or now()
    with engine.begin() as db:
        proposals=db.execute(text('SELECT id FROM agent_proposals WHERE run_id=:id'),{'id':identity}).scalars().all()
        db.execute(text("UPDATE agent_proposals SET status='failed' WHERE run_id=:id"),{'id':identity})
    import wandb
    entity,project=os.environ['WANDB_PROJECT'].split('/',1)
    os.environ['WANDB_ENTITY']=entity;os.environ['WANDB_PROJECT']=project
    api=wandb.Api(timeout=30)
    for proposal in proposals:
        path=ROOT/'data/verification/release'/f'launch-{proposal}.json'
        if not path.exists():continue
        receipt=json.loads(path.read_text())
        receipt.setdefault('pre_recovery_status',receipt['status'])
        receipt.update(status='failed',local_status='failed',recovered_at=now(),reason='Host graphics crash; execution quarantined',remote_status='not_read_back')
        atomic_json(path,receipt)
        try:
            remote=api.run('jerry-wen0616-santa-clara-university/neuroloop/'+receipt['wandb_run_id'])
            remote.summary['local_status']='failed';remote.summary['recovery_reason']='Windows graphics crash; execution paused; saved baseline preserved'
            remote.summary.update()
            fetched=api.run(remote.path[0]+'/'+remote.path[1]+'/'+remote.id)
            receipt.update(remote_state=fetched.state,remote_status='confirmed' if fetched.summary.get('local_status')=='failed' else 'unconfirmed')
        except Exception as exc:receipt.update(remote_status='readback_failed',remote_error=type(exc).__name__)
        atomic_json(path,receipt)
        print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
