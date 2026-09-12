"""Operational audit: real MCP, fresh bounded inference and independent stored-array checks.

Creates one explicitly named audit composition/project. Never substitutes neural output.
Reports failures as evidence; does not change credentials or installed dependencies.
"""
import asyncio, hashlib, io, json, os, sqlite3, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
import httpx
import numpy as np
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/verification/release' / os.getenv('NEUROLOOP_AUDIT_NAME','runtime-audit')
if not OUT.resolve().is_relative_to(ROOT/'data/verification/release'):
    raise ValueError('Audit output must stay within release verification')
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'backend'))
from neuroloop.readout import summarize, similarity

async def main():
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'checks': {}, 'calls': [], 'failures': []}
    def save():
        (OUT/'runtime.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    def check(name, value):
        report['checks'][name] = bool(value)
        if not value: report['failures'].append(name)
        save()
    with httpx.Client(base_url='http://127.0.0.1:8010', timeout=60) as http:
        check('unauthenticated_api_rejected', http.get('/api/dashboard').status_code == 401)
        check('unauthenticated_mcp_rejected', http.post('/mcp/', json={}).status_code == 401)
        check('cross_origin_session_rejected', http.post('/auth/local', headers={'Origin':'https://example.invalid','X-NeuroLoop-Local':'browser'}).status_code == 403)
        auth = http.post('/auth/local', headers={'Origin':'http://localhost:3010','X-NeuroLoop-Local':'browser'})
        auth.raise_for_status()
        headers = {'Authorization':'Bearer '+auth.json()['token']}
        http.headers.update(headers)
        async with httpx.AsyncClient(headers=headers, timeout=60) as client:
            async with streamable_http_client('http://127.0.0.1:8010/mcp/', http_client=client) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    report['http_tools'] = [t.name for t in (await session.list_tools()).tools]
                    r = await session.call_tool('get_capabilities', {})
                    check('http_mcp_real_capabilities', not r.isError)
        server = StdioServerParameters(command=str(ROOT/'.runtimes/app/Scripts/python.exe'), args=[str(ROOT/'scripts/mcp_stdio.py')], cwd=str(ROOT))
        with (OUT/'mcp-stderr.log').open('w', encoding='utf-8') as errors:
            async with stdio_client(server, errlog=errors) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    report['stdio_tools'] = [t.name for t in (await session.list_tools()).tools]
                    check('both_transports_discover_same_18_tools', len(report['stdio_tools']) == 18 and set(report['stdio_tools']) == set(report['http_tools']))
                    async def call(name, args=None):
                        r = await session.call_tool(name, args or {})
                        if r.isError: raise RuntimeError(name+': '+str(r.content))
                        report['calls'].append(name)
                        return r.structuredContent or json.loads(r.content[0].text)
                    report['hardware_before'] = await call('get_system_status')
                    report['capabilities'] = await call('get_capabilities')
                    workspace = await call('list_workspace')
                    check('workspace_has_real_assets', bool(workspace['assets']))
                    prior = json.loads((ROOT/'data/verification/refinement/real-media-report.json').read_text(encoding='utf-8'))
                    # New source-derived composition ensures this is not a reused whole evaluation.
                    rendered = await call('render_creative', {'asset_id':prior['assets']['image']['id'], 'headline':'NeuroLoop system audit', 'subline':datetime.now(timezone.utc).isoformat(), 'duration':6})
                    project = await call('create_project', {'name':'System audit / NASA composition', 'brief':'Six-second silent composition from the original NASA lunar photograph. Integration verification only.', 'asset_id':rendered['id']})
                    run = await call('evaluate_creative', {'project_id':project['id'], 'max_evaluations':1, 'no_speech':True})
                    report['fresh_project_id'] = project['id']; report['fresh_run_id'] = run['id']; save()
                    deadline = time.monotonic()+960; stage = ''
                    while time.monotonic() < deadline:
                        run = await call('get_run', {'run_id':run['id']})
                        if run['stage'] != stage:
                            stage=run['stage']; print(stage, flush=True)
                        if run['status'] not in ['queued','running']: break
                        await asyncio.sleep(3)
                    report['fresh_run'] = run
                    check('fresh_mcp_inference_completed', run['status']=='completed' and run['evaluations_used']==1)
                    if run['status'] != 'completed': raise RuntimeError(run.get('error') or run['stage'])
                    identity = run['result']['best_evaluation_id']
                    report['fresh_evidence'] = await call('get_evidence', {'evaluation_id':identity})
                    evaluations = await call('list_evaluations')
                    check('new_evaluation_visible_in_mcp', any(e['id']==identity for e in evaluations['evaluations']))
                    ids=[prior['evaluations'][k]['id'] for k in ['video','reference']]
                    report['comparison'] = await call('compare_creatives', {'evaluation_ids':ids})
                    report['export'] = await call('export_result', {'run_id':run['id']})
                    archive=http.get(report['export']['archive_path']); archive.raise_for_status()
                    (OUT/'fresh-output.zip').write_bytes(archive.content)
                    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
                        check('export_zip_integrity', z.testzip() is None)
                        report['export_members']=z.namelist()
                    ledger=await call('get_research_ledger')
                    check('new_result_visible_in_research', any(e['id']==identity for e in ledger['evaluations']))
        # Audit every recorded array and asset, including archived history.
        report['arrays']=[]; report['assets']=[]
        with sqlite3.connect('file:'+str(ROOT/'data/neuroloop.db')+'?mode=ro', uri=True) as db:
            db.row_factory=sqlite3.Row
            report['database_integrity']=db.execute('pragma integrity_check').fetchone()[0]
            arrays={}
            for row in db.execute('select * from evaluations'):
                try:
                    path=Path(row['prediction_path']); x=np.load(path, allow_pickle=False)
                    evidence=json.loads(row['evidence']); computed=summarize(x,evidence['times'])
                    matched=all(np.allclose(computed[k],evidence[k],atol=1e-7) for k in ['left_mean','right_mean','rms','range'])
                    frame=http.get('/api/evaluations/'+row['id']+'/frame?index=0'); frame.raise_for_status()
                    served=np.array_equal(np.asarray(frame.json()['values']),x[0])
                    arrays[row['id']]=x
                    report['arrays'].append({'id':row['id'],'path':str(path.relative_to(ROOT)),'shape':list(x.shape),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'summary_matches':matched,'api_frame_exact':served,'finite':bool(np.isfinite(x).all()),'nonconstant':bool(np.ptp(x)>0)})
                except Exception as exc:
                    report['failures'].append('array '+row['id']+': '+str(exc))
            for row in db.execute('select id,path,sha256 from assets'):
                p=Path(row['path']); actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
                report['assets'].append({'id':row['id'],'hash_matches':actual==row['sha256']})
            report['active_jobs']=db.execute("select count(*) from runs where status in ('queued','running')").fetchone()[0]
            report['run_status_counts']=dict(db.execute('select status,count(*) from runs group by status'))
        check('all_stored_arrays_match_summaries_and_served_frames', bool(report['arrays']) and all(all(e[k] for k in ['summary_matches','api_frame_exact','finite','nonconstant']) for e in report['arrays']))
        check('all_managed_asset_hashes_match', all(a['hash_matches'] for a in report['assets']))
        numerical=similarity(arrays[ids[0]],arrays[ids[1]])
        report['independently_recomputed_similarity']=numerical
        check('mcp_similarity_matches_saved_numpy_arrays', abs(numerical-report['comparison']['matrix'][0][1])<1e-10)
        check('database_integrity_and_idle_queue', report['database_integrity']=='ok' and report['active_jobs']==0)
        report['connections']=http.post('/api/connections/check').json()
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    report['passed']=not report['failures'] and all(report['checks'].values())
    report['calls']=sorted(set(report['calls'])); save()
    print(json.dumps({'passed':report['passed'],'checks':report['checks'],'array_count':len(report['arrays']),'asset_count':len(report['assets']),'fresh_run_id':report['fresh_run_id'],'failures':report['failures']},indent=2))

if __name__=='__main__': asyncio.run(main())
