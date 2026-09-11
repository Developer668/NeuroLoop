"""Read-only recovery audit. No media creation, neural execution or GPU imports."""
import asyncio,hashlib,json,sqlite3,sys
from pathlib import Path
from datetime import datetime,timezone
import httpx,numpy as np
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.readout import summarize

async def main():
    report={'at':datetime.now(timezone.utc).isoformat(),'neural_execution':False,'checks':{},'arrays':[],'assets':[]}
    def check(name,value):
        report['checks'][name]=bool(value)
    with httpx.Client(base_url='http://127.0.0.1:8010',timeout=45) as http:
        check('api_rejects_missing_auth',http.get('/api/dashboard').status_code==401)
        check('mcp_rejects_missing_auth',http.post('/mcp/',json={}).status_code==401)
        check('cross_origin_rejected',http.post('/auth/local',headers={'Origin':'https://example.invalid','X-NeuroLoop-Local':'browser'}).status_code==403)
        auth=http.post('/auth/local',headers={'Origin':'http://localhost:3010','X-NeuroLoop-Local':'browser'});auth.raise_for_status()
        headers={'Authorization':'Bearer '+auth.json()['token']};http.headers.update(headers)
        capabilities=http.get('/api/capabilities').json();check('persistent_execution_hold',capabilities['execution']['paused'])
        # Fail closed: this verification must never be used to submit model work.
        if not capabilities['execution']['paused']:raise RuntimeError('Expected a paused recovery workspace')
        async with httpx.AsyncClient(headers=headers,timeout=45) as client:
            async with streamable_http_client('http://127.0.0.1:8010/mcp/',http_client=client) as streams:
                async with ClientSession(streams[0],streams[1]) as session:
                    await session.initialize();report['http_tools']=[t.name for t in (await session.list_tools()).tools]
                    result=await session.call_tool('get_capabilities',{});check('http_capabilities_real',not result.isError)
        params=StdioServerParameters(command=str(ROOT/'.runtimes/app/Scripts/python.exe'),args=[str(ROOT/'scripts/mcp_stdio.py')],cwd=str(ROOT))
        async with stdio_client(params) as (reader,writer),ClientSession(reader,writer) as session:
            await session.initialize();report['stdio_tools']=[t.name for t in (await session.list_tools()).tools]
            check('transport_schemas_match',report['stdio_tools']==report['http_tools'])
            for name in ['get_system_status','get_research_ledger','list_evaluations']:
                result=await session.call_tool(name,{});check('stdio_'+name,not result.isError)
            result=await session.call_tool('evaluate_creative',{'project_id':'recovery-verification-must-not-execute'})
            check('mcp_queue_rejects_held_execution',result.isError and 'paused' in str(result.content))
        with sqlite3.connect('file:'+str(ROOT/'data/neuroloop.db')+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            check('sqlite_integrity',db.execute('pragma integrity_check').fetchone()[0]=='ok')
            check('no_active_runs',db.execute("select count(*) from runs where status in ('queued','running')").fetchone()[0]==0)
            for row in db.execute('select * from evaluations'):
                p=Path(row['prediction_path']);x=np.load(p,allow_pickle=False)
                evidence=json.loads(row['evidence']);computed=summarize(x,evidence['times'])
                frame=http.get('/api/evaluations/'+row['id']+'/frame?index=0');frame.raise_for_status()
                report['arrays'].append({'id':row['id'],'shape':list(x.shape),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'finite':bool(np.isfinite(x).all()),'nonconstant':bool(np.ptp(x)>0),'summary_matches':all(np.allclose(computed[k],evidence[k],atol=1e-7) for k in ['left_mean','right_mean','rms','range']),'api_frame_exact':bool(np.array_equal(np.asarray(frame.json()['values']),x[0]))})
            for row in db.execute('select id,path,sha256 from assets'):
                report['assets'].append({'id':row['id'],'hash_matches':hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256']})
        check('all_arrays_intact',bool(report['arrays']) and all(all(x[k] for k in ['finite','nonconstant','summary_matches','api_frame_exact']) for x in report['arrays']))
        check('all_assets_intact',all(x['hash_matches'] for x in report['assets']))
        report['connections']=http.post('/api/connections/check').json()
        manifest=json.loads((ROOT/'data/services.json').read_text())
        check('model_worker_and_launch_not_started',not any(x in manifest['children'] for x in ['worker','launch']))
        report['services']=list(manifest['children'])
        revoke=http.post('/auth/revoke');check('session_revocation',revoke.status_code==200 and http.get('/api/dashboard').status_code==401)
    target=ROOT/'data/verification/release/recovery-audit.json';target.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'checks':report['checks'],'arrays':len(report['arrays']),'assets':len(report['assets']),'report':str(target)},indent=2))
    if not all(report['checks'].values()):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
