"""Review the saved ARIA reply, approve its strict projection locally, submit one Launch job."""
import json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.agent_bridge import Proposal,propose
from neuroloop.db import engine,initialize
from sqlalchemy import text

if __name__=='__main__':
    initialize()
    target=ROOT/'data/verification/release/aria-submission.json'
    if target.exists():raise SystemExit('An ARIA submission receipt already exists; do not duplicate the approved run.')
    content=(ROOT/'data/verification/release/aria-review.txt').read_text(encoding='utf8')
    start=content.index('{ "version": 1, "source": "ARIA"')
    raw,_=json.JSONDecoder().raw_decode(content[start:])
    body=Proposal.model_validate({k:raw[k] for k in Proposal.model_fields})
    record=propose(body)
    # The parent task explicitly authorizes this bounded verification. The full
    # ARIA response remains on disk; only the reviewed five-field contract enters execution.
    with engine.begin() as db:db.execute(text("UPDATE agent_proposals SET status='approved' WHERE id=:id"),{'id':record['id']})
    manifest=json.loads((ROOT/'infrastructure/launch/installed.json').read_text())
    os.environ['WANDB_PROJECT']=manifest['project'];os.environ['WANDB_ENTITY']=manifest['entity']
    from wandb.sdk.launch import launch_add
    queued=launch_add(job=manifest['job'],config={'overrides':{'run_config':{'proposal_id':record['id']}}},project=manifest['project'],entity=manifest['entity'],queue_name=manifest['queue'],resource='local-process')
    receipt={'proposal':record,'queue_item_id':queued.id,'queue':manifest['queue'],'job':manifest['job'],'ignored_aria_fields':sorted(set(raw)-set(Proposal.model_fields))}
    target.write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({'proposal_id':record['id'],'queue_item_id':queued.id,'contract':record['specification']['request']},indent=2))
