"""W&B Launch agent restricted to NeuroLoop's installed versioned entrypoint.

The pinned SDK's LocalProcessRunner is adapted to argv-based Windows execution.
No queued shell, downloaded Python, Docker image, file override or arbitrary
resource target is executed. A proposal must already be approved in the local DB.
"""
from pathlib import Path
import asyncio,json,os,sys,threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.config import settings
settings()
from neuroloop.agent_bridge import get_proposal
from neuroloop.launch_contract import validate_spec as check_spec
from neuroloop import services
from filelock import FileLock
from wandb.sdk.launch import loader
from wandb.sdk.launch.runner.local_process import LocalProcessRunner
from wandb.sdk.launch.runner.local_container import LocalSubmittedRun,_thread_process_runner
from wandb.sdk.launch.agent.agent import LaunchAgent
from wandb.sdk.launch._launch import resolve_agent_config
from wandb.analytics import TelemetryRecorder

manifest=json.loads((ROOT/'infrastructure/launch/installed.json').read_text())
os.environ['WANDB_PROJECT']=manifest['project'];os.environ['WANDB_ENTITY']=manifest['entity']

def validate_spec(spec):
    from neuroloop.execution_guard import require_execution_enabled
    require_execution_enabled()
    return check_spec(spec,manifest,get_proposal)

class BoundedSubmittedRun(LocalSubmittedRun):
    def __init__(self,identity):
        super().__init__();self.proposal_id=identity

    async def cancel(self):
        proposal=get_proposal(self.proposal_id)
        if proposal.get('run_id'):services.cancel_run(proposal['run_id'])
        await super().cancel()

class BoundedRunner(LocalProcessRunner):
    async def run(self,project,*args,**kwargs):
        from neuroloop.execution_guard import require_execution_enabled
        require_execution_enabled()
        identity=project.override_config['proposal_id']
        proposal=get_proposal(identity)
        if proposal['status'] not in {'approved','queued'}:raise ValueError('Local approval is required')
        env=os.environ.copy();env.update(project.get_env_vars_dict(self._api,32000))
        env['NEUROLOOP_APPROVED_PROPOSAL']=identity
        # The installed entrypoint owns the strict schema and 960-second ceiling.
        command=[str(ROOT/'.runtimes/app/Scripts/python.exe'),'-u',str(ROOT/'scripts/launch_entry.py')]
        result=BoundedSubmittedRun(identity)
        thread=threading.Thread(target=_thread_process_runner,args=(result,command,str(ROOT),env))
        result.set_thread(thread);thread.start()
        return result

def runner(name,api,config,environment,registry):
    if name!='local-process':raise ValueError('Cloud and container runners are disabled in this agent')
    return BoundedRunner(api,config)

class BoundedAgent(LaunchAgent):
    def _assert_secure(self,spec):
        super()._assert_secure(spec);validate_spec(spec)

async def main():
    from neuroloop.execution_guard import require_execution_enabled
    require_execution_enabled()
    loader.runner_from_config=runner
    config,api=resolve_agent_config(manifest['entity'],1,(manifest['queue'],),None,0)
    config.update(secure_mode=True,max_jobs=1,max_schedulers=0,builder={'type':'noop'})
    agent=BoundedAgent(api,config,TelemetryRecorder())
    async def heartbeat():
        from neuroloop.persistence import atomic_json
        import time
        while True:
            atomic_json(ROOT/'data/launch-agent.json',{'pid':os.getpid(),'heartbeat':time.time(),'queue':manifest['queue'],'job':manifest['job'],'resource':'local-process'})
            await asyncio.sleep(10)
    pulse=asyncio.create_task(heartbeat())
    try:await agent.loop()
    finally:
        pulse.cancel()
        (ROOT/'data/launch-agent.json').unlink(missing_ok=True)

if __name__=='__main__':
    with FileLock(str(ROOT/'data/launch-agent.lock'),timeout=0):asyncio.run(main())
