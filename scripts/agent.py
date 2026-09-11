"""Review and submit bounded local jobs: propose FILE, show ID, submit ID --digest SHA256."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.agent_bridge import Proposal,propose,get_proposal
from neuroloop.db import engine,initialize
from neuroloop.persistence import atomic_json
from sqlalchemy import text

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['propose','show','submit'])
    p.add_argument('value');p.add_argument('--digest')
    a=p.parse_args();initialize()
    if a.action=='propose':
        result=propose(Proposal.model_validate_json(Path(a.value).read_text(encoding='utf8')))
    else:
        result=get_proposal(a.value)
        if a.action=='submit':
            from neuroloop.execution_guard import require_execution_enabled
            require_execution_enabled()
            if a.digest!=result['approval_digest']:p.error('Pass the SHA-256 digest from the reviewed proposal')
            destination=ROOT/'data/launch-submissions'/f'{result["id"]}.json'
            from filelock import FileLock
            destination.parent.mkdir(parents=True,exist_ok=True)
            with FileLock(str(destination)+'.lock',timeout=0):
                if destination.exists():p.error('Submission already recorded; inspect its receipt before retrying')
                manifest=json.loads((ROOT/'infrastructure/launch/installed.json').read_text())
                with engine.begin() as db:
                    db.execute(text("UPDATE agent_proposals SET status='approved' WHERE id=:id AND status='proposed'"),{'id':result['id']})
                os.environ['WANDB_PROJECT']=manifest['project'];os.environ['WANDB_ENTITY']=manifest['entity']
                from wandb.sdk.launch import launch_add
                # Persist intent first: an uncertain network outcome must never silently duplicate work.
                receipt={'proposal_id':result['id'],'status':'submitting','job':manifest['job'],'queue':manifest['queue']}
                atomic_json(destination,receipt)
                try:
                    queued=launch_add(job=manifest['job'],config={'overrides':{'run_config':{'proposal_id':result['id']}}},project=manifest['project'],entity=manifest['entity'],queue_name=manifest['queue'],resource='local-process')
                    receipt.update(status='submitted',queue_item_id=queued.id)
                except Exception as exc:
                    receipt.update(status='outcome_uncertain',error=type(exc).__name__)
                    atomic_json(destination,receipt);raise
                atomic_json(destination,receipt);result=receipt
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
