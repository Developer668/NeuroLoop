"""One explicitly authorized CPU verification via real MCP and shared worker.

Run with the model runtime. Never starts the general queue or clears a hold.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]


async def queue(project_id, include_tsam, include_kragel):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    app_python=ROOT/'.runtimes/app'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    parameters=StdioServerParameters(command=str(app_python),args=[str(ROOT/'scripts/mcp_stdio.py')],env=dict(os.environ))
    async with stdio_client(parameters) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            result=await client.call_tool('evaluate_creative',{'project_id':project_id,'max_evaluations':1,
                'no_speech':True,'allow_static_presentation':True,'include_tsam':include_tsam,
                'include_kragel':include_kragel,
                'tsam_research_acknowledged':include_tsam,'idempotency_key':'cpu-verify/'+str(uuid.uuid4())})
            if result.isError:
                raise RuntimeError(str(result.content))
            if result.structuredContent:
                return result.structuredContent
            return json.loads(next(item.text for item in result.content if hasattr(item,'text')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-id',required=True)
    parser.add_argument('--max-seconds',type=int,default=300)
    parser.add_argument('--cpu-threads',type=int,choices=range(1,9),default=4)
    parser.add_argument('--include-tsam',action='store_true')
    parser.add_argument('--include-kragel',action='store_true')
    args=parser.parse_args()
    if not 30<=args.max_seconds<=600:
        parser.error('--max-seconds must be between 30 and 600')
    if 'torch' in sys.modules:
        raise RuntimeError('Run in a fresh process before torch is imported')
    os.environ.update(NEUROLOOP_CPU_VERIFICATION='true',NEUROLOOP_INFERENCE_DEVICE='cpu',
        CUDA_VISIBLE_DEVICES='-1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',
        OMP_NUM_THREADS=str(args.cpu_threads),MKL_NUM_THREADS=str(args.cpu_threads),NEUROLOOP_CPU_THREADS=str(args.cpu_threads),
        NEUROLOOP_MODEL_TIMEOUT_SECONDS=str(args.max_seconds))
    model_python=ROOT/'.runtimes/model'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    os.environ['NEUROLOOP_MODEL_PYTHON']=str(model_python)
    sys.path.insert(0,str(ROOT/'backend'))
    from neuroloop import execution_guard
    if not execution_guard.cpu_verification_enabled():
        raise RuntimeError('CPU verification bootstrap refused')
    from neuroloop.config import settings
    if Path(sys.executable).resolve()!=settings().model_python.resolve():
        raise RuntimeError('Use the configured model runtime for this verifier')
    from neuroloop.hardware import require_inference_headroom
    require_inference_headroom()
    from filelock import FileLock
    from neuroloop.db import Session,Run,Evaluation,Asset,now
    from neuroloop import worker,delivery
    from neuroloop.persistence import validate_artifact_manifest,atomic_json
    hold=settings().data/'inference-quarantine.json'
    hold_before=hold.read_bytes() if hold.exists() else None
    run_id=None
    receipt={'scope':'fresh CPU-only single-run verification via MCP','project_id':args.project_id,
             'started_at':now(),'max_seconds':args.max_seconds,'cpu_threads':args.cpu_threads,
             'gpu_allowed':False,'minimum_free_ram_gib':4}
    try:
        with FileLock(settings().data/'gpu-worker.lock').acquire(timeout=0):
            queued=asyncio.run(asyncio.wait_for(queue(args.project_id,args.include_tsam,args.include_kragel),timeout=60))
            run_id=queued.get('id') or queued.get('run_id')
            if not run_id:
                raise RuntimeError('MCP response has no run identity')
            receipt['mcp_result']=queued
            with Session.begin() as db:
                run=db.get(Run,run_id)
                if not run or run.status!='queued' or run.project_id!=args.project_id:
                    raise RuntimeError('New MCP run is not claimable')
                run.status='running';run.owner=f'cpu-verifier-{os.getpid()}'
                run.started_at=now();run.heartbeat=now()
            worker.supervise_run(run_id)
            with Session() as db:
                run=db.get(Run,run_id)
                receipt.update(run_id=run_id,status=run.status,error=run.error,result=run.result)
                if run.status!='completed':
                    raise RuntimeError(run.error or run.stop_reason or 'Run did not complete')
                evaluation=db.get(Evaluation,run.result.get('baseline_evaluation_id'))
                if not evaluation or evaluation.created_at<run.started_at:
                    raise RuntimeError('No freshly computed evaluation; cached evidence does not close this check')
                import numpy as np
                array=np.load(evaluation.prediction_path,allow_pickle=False,mmap_mode='r')
                if not np.isfinite(array).all() or list(array.shape)!=evaluation.evidence.get('shape'):
                    raise RuntimeError('Prediction is nonfinite or has mismatched shape')
                if evaluation.evidence.get('device')!='cpu':
                    raise RuntimeError('Saved prediction did not report CPU execution')
                asset=db.get(Asset,evaluation.asset_id)
                validate_artifact_manifest(Path(evaluation.prediction_path).parent,cache_key=evaluation.cache_key,
                    profile=evaluation.profile,asset_sha256=asset.sha256)
                receipt.update(evaluation_id=evaluation.id,shape=list(array.shape),all_finite=True,
                    prediction_sha256=hashlib.sha256(Path(evaluation.prediction_path).read_bytes()).hexdigest(),manifest_verified=True)
                receipt['readouts']={}
                for name,requested in (('tsam',args.include_tsam),('kragel',args.include_kragel)):
                    if requested:
                        readout=evaluation.evidence.get(name,{})
                        receipt['readouts'][name]={key:readout.get(key) for key in ('status','reason','registration_verified','decision_eligible')}
                        if readout.get('status')!='experimental':
                            raise RuntimeError(f'{name} requested but did not complete: {readout.get("reason","missing readout")}')
            delivery.drain(limit=5)
            receipt['external_receipts']=delivery.receipts(limit=10)
            receipt['passed']=True
    except Exception as exc:
        receipt.update(passed=False,error=str(exc),run_id=run_id)
        if run_id:
            worker.finish_interrupted(run_id,str(exc))
    finally:
        receipt['gpu_hold_unchanged']=(hold.read_bytes() if hold.exists() else None)==hold_before
        if not receipt['gpu_hold_unchanged']:
            receipt['passed']=False;receipt['hold_error']='GPU hold changed during verification; inspect before any further work'
        receipt['finished_at']=now()
        destination=ROOT/'artifacts/refresh-verification'/f'cpu-run-{run_id or uuid.uuid4()}.json'
        atomic_json(destination,receipt)
        print(json.dumps({'passed':receipt.get('passed',False),'run_id':run_id,'receipt':str(destination),'error':receipt.get('error')}))
    return 0 if receipt.get('passed') else 1


if __name__=='__main__':
    raise SystemExit(main())
