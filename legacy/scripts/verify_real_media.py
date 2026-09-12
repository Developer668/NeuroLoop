"""Real NASA media through the MCP stdio interface used by Codex. No mocked output."""
import asyncio,json,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
import httpx
import numpy as np
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verification/refinement'
MEDIA=OUT/'real-media'

async def main():
    report={'started_at':datetime.now(timezone.utc).isoformat(),'transport':'MCP stdio, same command configured for Codex','tool_calls':[],'runs':{},'evaluations':{},'passed':False}
    if (OUT/'real-media-report.json').exists():
        report=json.loads((OUT/'real-media-report.json').read_text(encoding='utf-8'))
    def save(): (OUT/'real-media-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def log(message): print(message,flush=True)
    with httpx.Client(base_url='http://127.0.0.1:8010',timeout=90) as http:
        auth=http.post('/auth/local',headers={'Origin':'http://localhost:3010','X-NeuroLoop-Local':'browser'});auth.raise_for_status()
        http.headers['Authorization']='Bearer '+auth.json()['token']
        paths={'video':MEDIA/'apollo-11-descent-20-30s.mp4','reference':MEDIA/'apollo-11-descent-30-40s.mp4','audio':MEDIA/'apollo-11-armstrong-original.mp3','image':MEDIA/'apollo-11-lunar-flag.jpg'}
        uploads={}
        for kind,path in paths.items():
            if kind in report.get('assets',{}):
                uploads[kind]=report['assets'][kind];continue
            with path.open('rb') as f:r=http.post('/api/assets',files={'file':(path.name,f)})
            r.raise_for_status();uploads[kind]=r.json()
        report['assets']={k:{'id':v['id'],'name':v['name'],'sha256':v['sha256']} for k,v in uploads.items()}
        save()
        server=StdioServerParameters(command=str(ROOT/'.venv/Scripts/python.exe'),args=[str(ROOT/'scripts/mcp_stdio.py')],cwd=str(ROOT))
        async with stdio_client(server) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools=await session.list_tools();report['discovered_tools']=[t.name for t in tools.tools]
                async def call(name,arguments=None):
                    response=await session.call_tool(name,arguments or {})
                    if response.isError:raise RuntimeError(name+': '+str(response.content))
                    report['tool_calls'].append(name)
                    return response.structuredContent or json.loads(response.content[0].text)
                async def wait_run(run,label):
                    last='';identity=run['id']
                    for _ in range(360):
                        result=await call('get_run',{'run_id':identity})
                        if result['stage']!=last:log(label+': '+result['stage']);last=result['stage']
                        if result['status'] not in ['queued','running']:
                            report['runs'][label]=result;save()
                            if result['status']!='completed':raise RuntimeError(label+': '+str(result.get('error')))
                            ev=await call('get_evidence',{'evaluation_id':result['result']['best_evaluation_id']})
                            report['evaluations'][label]=ev;save()
                            frame=http.get('/api/evaluations/'+ev['id']+'/frame');frame.raise_for_status()
                            assert len(frame.json()['values'])==20484 and np.isfinite(frame.json()['values']).all()
                            return result,ev
                        await asyncio.sleep(3)
                    raise TimeoutError(label+' did not complete within the bounded check')
                await call('get_capabilities');await call('get_system_status');await call('list_workspace')
                projects={}
                for kind in ['video','reference','audio','image']:
                    project=report.get('projects',{}).get(kind) or await call('create_project',{'name':{'video':'Apollo 11 / Lunar descent','reference':'Apollo 11 / First step sequence','audio':'Apollo 11 / Armstrong recording','image':'Apollo 11 / Lunar photograph'}[kind],'brief':'Real NASA Apollo 11 source media. Local integration verification; no claim of advertising effectiveness or measured human response. Video excerpts retain source timestamps in their filename.','asset_id':uploads[kind]['id'],'reference_ids':[uploads['reference']['id']] if kind=='video' else []})
                    projects[kind]=project;report['projects']=projects;save()
                    if report.get('runs',{}).get(kind,{}).get('status')=='completed':continue
                    run=await call('evaluate_creative',{'project_id':project['id'],'max_evaluations':2 if kind=='video' else 1,'allow_static_presentation':kind=='image','include_tsam':kind=='video','tsam_research_acknowledged':kind=='video'})
                    await wait_run(run,kind)
                evaluations=await call('list_evaluations');assert len(evaluations['evaluations'])>=4
                ids=[report['evaluations'][kind]['id'] for kind in ['video','reference']]
                report['comparison']=await call('compare_creatives',{'evaluation_ids':ids})
                assert np.isfinite(report['comparison']['matrix']).all()
                actual=http.post('/api/compare',json={'evaluation_ids':ids});actual.raise_for_status()
                assert np.allclose(actual.json()['matrix'],report['comparison']['matrix'])
                report['render']=await call('render_creative',{'asset_id':uploads['image']['id'],'headline':'One small step','subline':'Apollo 11 / NASA archive','duration':5,'aspect':'landscape'})
                experiment=await call('run_experiment',{'project_id':projects['video']['id'],'operator':'contrast_up','max_evaluations':3,'max_seconds':900})
                result,ev=await wait_run(experiment,'experiment')
                export=await call('export_result',{'run_id':result['id']})
                archive=http.get(export['archive_path']);archive.raise_for_status();assert archive.content[:2]==b'PK'
                report['export_bytes']=len(archive.content)
                cancelled=await call('optimize_creative',{'project_id':projects['video']['id'],'max_evaluations':3,'max_seconds':30})
                cancellation=await call('cancel_run',{'run_id':cancelled['id']})
                for _ in range(30):
                    cancellation=await call('get_run',{'run_id':cancelled['id']})
                    if cancellation['status'] not in ['queued','running']:break
                    await asyncio.sleep(1)
                assert cancellation['status']=='cancelled'
                report['cancellation']={'run_id':cancelled['id'],'status':cancellation['status']}
                research=await call('get_research_ledger');assert research['totals']['evaluations']>=4
                report['research_totals']=research['totals']
        report['connections']=http.post('/api/connections/check').json()
        report['tool_calls']=sorted(set(report['tool_calls']))
        assert set(report['tool_calls'])==set(report['discovered_tools'])
        report['passed']=True;report['finished_at']=datetime.now(timezone.utc).isoformat();save()
        log('PASSED: real video, audio, image, comparison, experiment, export, cancellation and all '+str(len(report['tool_calls']))+' MCP tools.')

if __name__=='__main__':asyncio.run(main())
