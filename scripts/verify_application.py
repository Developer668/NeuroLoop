"""Exercise the real HTTP/MCP/GPU path. Fixtures are labelled technical, not human evidence."""
from pathlib import Path
import asyncio,json,sys,time
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.media import execute

async def verify_mcp(token):
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession
    async with streamablehttp_client('http://127.0.0.1:8010/mcp/',headers={'Authorization':'Bearer '+token}) as streams:
        async with ClientSession(streams[0],streams[1]) as session:
            await session.initialize()
            tools=await session.list_tools()
            names=[x.name for x in tools.tools]
            assert 'evaluate_creative' in names and 'get_evidence' in names
            response=await session.call_tool('get_capabilities',{})
            assert not response.isError
            return {'initialized':True,'tools':names,'capabilities_call_passed':True}

def main():
    folder=ROOT/'data/verification';folder.mkdir(exist_ok=True)
    source=folder/'technical-motion-fixture.mp4'
    if not source.is_file():raise RuntimeError('Run verify_real_tribe.py first')
    reference=folder/'technical-reference.mp4'
    execute(['-y','-i',str(source),'-vf','eq=contrast=1.15:brightness=0.05','-an','-c:v','libx264','-pix_fmt','yuv420p',str(reference)])
    client=httpx.Client(base_url='http://127.0.0.1:8010',timeout=180)
    assert client.get('/api/dashboard').status_code==401
    auth=client.post('/auth/local',headers={'Origin':'http://localhost:3010','X-NeuroLoop-Local':'browser'});auth.raise_for_status()
    token=auth.json()['token'];client.headers['Authorization']='Bearer '+token
    uploads=[]
    for path in [source,reference]:
        with path.open('rb') as handle:
            response=client.post('/api/assets',files={'file':(path.name,handle,'video/mp4')})
        response.raise_for_status();uploads.append(response.json())
    project=client.post('/api/projects',json={'name':'Technical verification — real cortical pipeline','brief':'A labelled technical motion fixture tests integration only. It is not a human-preference or advertising-effectiveness benchmark.','asset_id':uploads[0]['id'],'reference_ids':[uploads[1]['id']],'constraints':{'preserve_duration':True,'preserve_audio':True,'max_filter_edits':2}})
    project.raise_for_status();pid=project.json()['id']
    payload={'project_id':pid,'mode':'optimize','max_evaluations':4,'max_seconds':600,'min_gain':0.0001,'target_score':1.0,'no_speech':True,'operators':['brightness_up','contrast_up']}
    response=client.post('/api/runs',json=payload,headers={'Idempotency-Key':'verify-'+pid});print('RUN_RESPONSE',response.status_code,response.text if response.status_code!=202 else 'accepted',flush=True);response.raise_for_status();run_id=response.json()['id']
    repeat=client.post('/api/runs',json=payload,headers={'Idempotency-Key':'verify-'+pid});assert repeat.json()['id']==run_id
    print('RUN',run_id,flush=True)
    deadline=time.monotonic()+660;last=''
    while time.monotonic()<deadline:
        response=client.get('/api/runs/'+run_id);response.raise_for_status();run=response.json()
        if run['stage']!=last:print(run['stage'],flush=True);last=run['stage']
        if run['status'] not in {'queued','running'}:break
        time.sleep(2)
    else:raise TimeoutError('Run did not finish within verification limit')
    (folder/'application-run.json').write_text(json.dumps(run,indent=2))
    if run['status']!='completed':raise RuntimeError(run.get('error') or run['stage'])
    assert run['result'].get('best_evaluation_id')
    ev=client.get('/api/evaluations/'+run['result']['best_evaluation_id']);ev.raise_for_status()
    frame=client.get('/api/evaluations/'+ev.json()['id']+'/frame?index=0');frame.raise_for_status();assert len(frame.json()['values'])==20484
    archive=client.get('/api/runs/'+run_id+'/export');archive.raise_for_status();assert archive.content[:2]==b'PK'
    mcp=asyncio.run(verify_mcp(token))
    output={'passed':True,'run_id':run_id,'project_id':pid,'authentication_rejected_missing_token':True,'idempotency_passed':True,'real_evaluations':run['evaluations_used'],'experiments':len(run['experiments']),'decisions':[x['decision'] for x in run['experiments']],'baseline_score':run['result']['baseline_metric']['value'],'best_score':run['result']['best_metric']['value'],'compute_seconds':run['compute_seconds'],'prediction_shape':ev.json()['evidence']['shape'],'export_bytes':len(archive.content),'mcp':mcp,'scope':'Technical pipeline verification on synthetic media input. Neural outputs are actual frozen-checkpoint inference; no human-response effectiveness is established.'}
    (folder/'application-e2e.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2),flush=True)
if __name__=='__main__':main()
