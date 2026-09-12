"""Register the reviewed local-only Launch contract and queue in the selected W&B team."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
entity,project=os.environ['WANDB_PROJECT'].split('/',1)
os.environ['WANDB_PROJECT']=project;os.environ['WANDB_ENTITY']=entity
import wandb
from wandb.sdk.launch.create_job import create_job

if __name__=='__main__':
    destination=ROOT/'infrastructure/launch/installed.json'
    if destination.exists():raise SystemExit('Launch contract is already registered; inspect installed.json before versioning another job.')
    api=wandb.Api()
    queue=api.create_run_queue('neuroloop-local-v1','local-process',entity=entity)
    job=create_job(path=str(ROOT/'infrastructure/launch'),job_type='code',entity=entity,project=project,name='neuroloop-bounded-v1',description='Fixed local approved-proposal bridge. No cloud compute; use NeuroLoop restricted Launch agent.',entrypoint='job.py',runtime='3.11')
    if job is None:raise RuntimeError('Job creation did not return an artifact')
    result={'version':1,'entity':entity,'project':project,'queue':queue.name,'job':f'{entity}/{project}/{job.name}','artifact_digest':job.digest,'resource':'local-process','sdk':'wandb==0.30.0'}
    destination.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))
