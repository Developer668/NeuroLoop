"""Execute exactly one explicitly selected queued run on CPU, never the general queue."""
import argparse, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--proposal-id')
    args=parser.parse_args()
    if 'torch' in sys.modules: raise RuntimeError('Use a fresh CPU-only process')
    os.environ.update(CUDA_VISIBLE_DEVICES='-1',NEUROLOOP_CPU_VERIFICATION='true',NEUROLOOP_INFERENCE_DEVICE='cpu',NEUROLOOP_CPU_THREADS='4',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',NEUROLOOP_MODEL_TIMEOUT_SECONDS='600')
    sys.path.insert(0,str(ROOT/'backend'))
    from neuroloop.config import settings
    from neuroloop.db import Session,Run,now
    from neuroloop import worker,services
    from neuroloop.execution_guard import cpu_verification_enabled
    from neuroloop.hardware import require_inference_headroom
    from filelock import FileLock
    if Path(sys.executable).resolve()!=settings().model_python.resolve() or not cpu_verification_enabled():
        raise RuntimeError('Canonical CPU model runtime required')
    hold=settings().data/'inference-quarantine.json'
    original_hold=hold.read_bytes() if hold.exists() else None
    with FileLock(settings().data/'gpu-worker.lock').acquire(timeout=0):
        require_inference_headroom()
        with Session.begin() as db:
            run=db.get(Run,args.run_id)
            if not run or run.status!='queued': raise ValueError('Selected run is not queued')
            request=run.config['request']
            if request['max_seconds']>600 or request['max_evaluations']>4: raise ValueError('CPU acceptance budget exceeded')
            if args.proposal_id:
                from neuroloop.agent_bridge import get_proposal
                proposal=get_proposal(args.proposal_id)
                if proposal.get('run_id')!=run.id or (run.config.get('agent_contract') or {}).get('proposal_id')!=args.proposal_id:
                    raise ValueError('Run does not belong to selected approved proposal')
            run.status='running';run.owner=f'owned-cpu-{os.getpid()}';run.started_at=now();run.heartbeat=now()
        worker.supervise_run(args.run_id)
    if (hold.read_bytes() if hold.exists() else None)!=original_hold: raise RuntimeError('GPU hold changed')
    run=services.get_run(args.run_id)
    print(json.dumps({'run_id':run['id'],'status':run['status'],'stop_reason':run.get('stop_reason'),'experiments':len(run.get('experiments',[]))}))
    return 0 if run['status']=='completed' else 1

if __name__=='__main__':raise SystemExit(main())
