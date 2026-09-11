"""Authenticated HTTP API and MCP server. Shared domain state; no demo fixtures seeded."""
from __future__ import annotations
import asyncio, json, mimetypes, secrets, zipfile
from contextlib import asynccontextmanager
from pathlib import Path
import numpy as np
from fastapi import FastAPI,UploadFile,File,Request,HTTPException
from fastapi.responses import JSONResponse,FileResponse,StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from .config import settings
from .db import initialize,Session,Asset,Project,Run,Evaluation,Experiment,RunEvent,as_dict,uid
from . import services,policy
from .schemas import ProjectCreate,RunCreate,CreativeCreate,CompareRequest,TranscriptUpdate
from .media import SUFFIXES,MediaError
from .mcp_server import mcp
from .readout import similarity,METRIC

from .auth import verify_token,issue_local_session

s=settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    async def export_loop():
        from .delivery import drain
        while True:
            await asyncio.sleep(15)
            try:
                await run_in_threadpool(drain)
            except Exception:
                import logging
                logging.getLogger(__name__).error('External delivery worker failed; receipts retained')
    exporter=asyncio.create_task(export_loop())
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        exporter.cancel()
        import contextlib
        with contextlib.suppress(asyncio.CancelledError):
            await exporter

app=FastAPI(title='NeuroLoop',version='0.1.0',description='Controlled creative experiments with explicit model evidence and no synthetic success data.',lifespan=lifespan,docs_url='/api/docs',openapi_url='/api/openapi.json')
app.add_middleware(CORSMiddleware,allow_origins=[s.frontend_origin,s.frontend_origin.replace('localhost','127.0.0.1')],allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Authorization','Content-Type','Idempotency-Key','Last-Event-ID'])

@app.middleware('http')
async def access_boundary(request: Request,call_next):
    if request.url.path not in {'/health','/auth/local'} and request.method!='OPTIONS':
        supplied=request.headers.get('authorization','')
        if not supplied.startswith('Bearer ') or not verify_token(supplied[7:]):
            return JSONResponse({'detail':'Valid NeuroLoop authorization is required'},status_code=401,headers={'WWW-Authenticate':'Bearer'})
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    return response

@app.exception_handler(services.DomainError)
async def domain_error(request: Request,exc: services.DomainError):
    return JSONResponse({'detail':str(exc)},status_code=400)

@app.exception_handler(MediaError)
async def media_error(request: Request,exc: MediaError):
    return JSONResponse({'detail':str(exc)},status_code=422)

@app.post('/auth/local')
def local_session(request: Request):
    allowed_origins={s.frontend_origin,s.frontend_origin.replace('localhost','127.0.0.1')}
    if s.host not in {'127.0.0.1','localhost'} or not request.client or request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403,'Local session exchange is disabled for remote deployments')
    if request.headers.get('origin') not in allowed_origins or request.headers.get('x-neuroloop-local')!='browser':
        raise HTTPException(403,'A same-origin local browser session is required')
    if request.url.hostname not in {'localhost','127.0.0.1','testserver'}:
        raise HTTPException(403,'Host is not a trusted loopback endpoint')
    return {'token':issue_local_session(),'expires_in':28800}

@app.get('/health')
def health():
    return {'status':'ok','service':'neuroloop','version':'0.1.0'}

@app.post('/auth/revoke')
def revoke_session(request: Request):
    from .auth import revoke_session
    return {'revoked':revoke_session(request.headers.get('authorization','')[7:])}

@app.get('/api/connections/receipts')
def delivery_receipts():
    from .delivery import receipts
    return {'receipts':receipts()}

from pydantic import BaseModel,Field,ConfigDict
class NeuroCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    command: str=Field(min_length=1,max_length=2500)

@app.post('/api/neuro/command')
def neuro_command(body: NeuroCommand):
    from .neuro import command
    return command(body.command)

from .agent_bridge import Proposal
@app.post('/api/agent/proposals')
def propose_agent_work(body: Proposal):
    from .agent_bridge import propose
    return propose(body)

@app.get('/api/agent/proposals/{identity}')
def read_agent_proposal(identity: str):
    from .agent_bridge import get_proposal
    return get_proposal(identity)

class ProposalApproval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    approval_digest: str=Field(pattern=r'^[a-f0-9]{64}$')

@app.post('/api/agent/proposals/{identity}/execute')
def execute_agent_work(identity: str,body: ProposalApproval):
    from .agent_bridge import execute
    return execute(identity,body.approval_digest)

@app.get('/api/dashboard')
def dashboard(): return services.dashboard()

@app.get('/api/capabilities')
def capabilities(): return services.capabilities()

@app.get('/api/system')
def system_status():
    from .hardware import hardware_status
    return hardware_status()

from .schemas import WorkspacePreferences

@app.get('/api/preferences')
def get_preferences():
    path=s.data/'preferences.json'
    return WorkspacePreferences.model_validate_json(path.read_text(encoding='utf-8')).model_dump() if path.is_file() else WorkspacePreferences().model_dump()

@app.put('/api/preferences')
def save_preferences(body: WorkspacePreferences):
    from .persistence import atomic_json
    atomic_json(s.data/'preferences.json',body.model_dump())
    return body.model_dump()

@app.get('/api/policy')
def policies(): return {'statistics':policy.history(),'meaning':'Recorded operator performance within a fixed context; not learned human psychology.'}

@app.get('/api/research')
def research_ledger():
    from .research import ledger
    return ledger()

@app.post('/api/connections/check')
def check_integrations():
    from .integrations import check_connections
    return check_connections()

@app.post('/api/projects',status_code=201)
def create_project(body: ProjectCreate): return services.create_project(body)

@app.put('/api/projects/{identity}')
def update_project(identity: str,body: ProjectCreate): return services.update_project(identity,body)

@app.get('/api/projects/{identity}')
def project(identity: str):
    with Session() as db:
        row=db.get(Project,identity)
        if not row: raise HTTPException(404,'Project not found')
        return as_dict(row)

@app.post('/api/assets',status_code=201)
async def upload(file: UploadFile=File(...)):
    name=(file.filename or 'upload').replace('\\','/').split('/')[-1][:240]
    suffix=Path(name).suffix.lower()
    if suffix not in SUFFIXES: raise HTTPException(415,'Supported inputs: video, audio, PNG/JPEG/WebP images, UTF-8 text')
    target=s.data/'assets'/f'{uid()}{suffix}';size=0
    try:
        with target.open('xb') as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>s.max_upload_bytes: raise HTTPException(413,'Upload exceeds the configured size limit')
                output.write(chunk)
        if size==0: raise HTTPException(400,'Empty uploads are not accepted')
        return await run_in_threadpool(services.register_asset,target,name,SUFFIXES[suffix])
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally: await file.close()

@app.put('/api/assets/{identity}/transcript')
def update_transcript(identity: str,body: TranscriptUpdate):
    with Session.begin() as db:
        item=db.get(Asset,identity)
        if not item: raise HTTPException(404,'Asset not found')
        if item.kind not in {'audio','video','text'}: raise HTTPException(422,'Timed words require audio, video, or text')
        words=[w.model_dump() for w in body.words]
        if any(words[i]['start']>words[i+1]['start'] for i in range(len(words)-1)):
            raise HTTPException(422,'Timed words must be in chronological order')
        duration=item.details.get('duration')
        if duration and any(w['end']>duration+0.1 for w in words):
            raise HTTPException(422,'A word extends beyond the source duration')
        if item.kind=='text':
            actual=Path(item.path).read_text(encoding='utf8')
            normalized=lambda value: ' '.join(value.split())
            if normalized(actual)!=normalized(' '.join(w['text'] for w in words)):
                raise HTTPException(422,'Timed words must preserve the exact source text')
        item.details={**item.details,'transcript':words,'transcript_source':'user-supplied timed words'}
        return as_dict(item,('path',))

@app.get('/api/assets/{identity}')
def asset(identity: str):
    with Session() as db:
        row=db.get(Asset,identity)
        if not row: raise HTTPException(404,'Asset not found')
        return as_dict(row,('path',))

def asset_file(identity: str,preview: bool=False) -> Path:
    with Session() as db:
        row=db.get(Asset,identity)
        if not row: raise HTTPException(404,'Asset not found')
        path=s.data/'assets'/row.details.get('preview','missing') if preview else Path(row.path)
    path=path.resolve()
    if not path.is_relative_to(s.data.resolve()) or not path.is_file(): raise HTTPException(404,'Managed file not found')
    return path

@app.get('/api/assets/{identity}/content')
def content(identity: str,download: bool=False):
    path=asset_file(identity)
    return FileResponse(path,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',filename=path.name if download else None,headers={'Cache-Control':'private, max-age=3600'})

@app.get('/api/assets/{identity}/preview')
def preview(identity: str):
    return FileResponse(asset_file(identity,True),media_type='image/jpeg',headers={'Cache-Control':'private, max-age=3600'})

@app.post('/api/creatives',status_code=201)
async def creative(body: CreativeCreate):
    return await run_in_threadpool(services.create_creative,body)

@app.post('/api/runs',status_code=202)
def create_run(body: RunCreate,request: Request):
    return services.create_run(body,request.headers.get('idempotency-key'))

@app.get('/api/runs/{identity}')
def run(identity: str): return services.get_run(identity)

@app.post('/api/runs/{identity}/cancel')
def cancel(identity: str): return services.cancel_run(identity)

@app.get('/api/runs/{identity}/events/stream')
async def stream(identity: str,request: Request):
    services.get_run(identity)
    try: cursor=int(request.headers.get('last-event-id','0'))
    except ValueError: cursor=0
    async def generate():
        nonlocal cursor
        while not await request.is_disconnected():
            with Session() as db:
                rows=db.scalars(select(RunEvent).where(RunEvent.run_id==identity,RunEvent.id>cursor).order_by(RunEvent.id)).all()
                current=db.get(Run,identity)
            for row in rows:
                cursor=row.id
                yield f'id: {row.id}\nevent: progress\ndata: {json.dumps(as_dict(row))}\n\n'
            if current.status not in {'queued','running'}:
                yield 'event: done\ndata: {}\n\n';break
            yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.get('/api/evaluations/{identity}')
def evidence(identity: str):
    with Session() as db:
        row=db.get(Evaluation,identity)
        if not row: raise HTTPException(404,'Evaluation not found')
        return as_dict(row,('prediction_path',))

@app.get('/api/evaluations/{identity}/frame')
def neural_frame(identity: str,index: int=0,reference: str | None=None):
    with Session() as db: row=db.get(Evaluation,identity)
    if not row or not row.prediction_path: raise HTTPException(404,'Neural array not found')
    path=Path(row.prediction_path).resolve()
    if not path.is_relative_to(s.data.resolve()): raise HTTPException(403,'Invalid managed result')
    array=np.load(path,mmap_mode='r',allow_pickle=False)
    if not 0<=index<len(array): raise HTTPException(400,'Frame index is outside the saved prediction')
    values=array[index];value_range=row.evidence['range']
    if reference:
        with Session() as db: baseline=db.get(Evaluation,reference)
        if not baseline or not baseline.prediction_path: raise HTTPException(404,'Reference array not found')
        if baseline.profile!=row.profile: raise HTTPException(409,'Difference requires matching model profiles')
        if baseline.evidence['times']!=row.evidence['times']:
            raise HTTPException(409,'Difference requires identical recorded timestamps; no implicit time warping is applied')
        baseline_path=Path(baseline.prediction_path).resolve()
        if not baseline_path.is_relative_to(s.data.resolve()): raise HTTPException(403,'Invalid managed result')
        other=np.load(baseline_path,allow_pickle=False,mmap_mode='r')
        if other.shape!=array.shape: raise HTTPException(409,'Difference requires matching array shapes')
        delta=np.asarray(array)-np.asarray(other)
        values=delta[index];value_range=[float(delta.min()),float(delta.max())]
    return {'evaluation_id':identity,'reference_id':reference,'index':index,'time':row.evidence['times'][index],
            'mesh':'fsaverage5','values':values.tolist(),'range':value_range}

@app.get('/api/geometry')
def geometry():
    path=s.data/'geometry/fsaverage5.json'
    if not path.is_file(): raise HTTPException(503,'Verified cortical geometry has not been prepared')
    return FileResponse(path,media_type='application/json',headers={'Cache-Control':'private, max-age=86400'})

@app.get('/api/evaluations/{identity}/regions')
def neural_regions(identity: str):
    from .anatomy import summarize_regions
    with Session() as db: row=db.get(Evaluation,identity)
    if not row or not row.prediction_path: raise HTTPException(404,'Neural array not found')
    path=Path(row.prediction_path).resolve()
    if not path.is_relative_to(s.data.resolve()): raise HTTPException(403,'Invalid managed result')
    if not (s.data/'geometry/atlas.json').is_file(): raise HTTPException(503,'Anatomical atlas is not installed')
    return {**summarize_regions(np.load(path,allow_pickle=False)), 'times':row.evidence['times']}

@app.get('/api/connections/mcp/config')
def mcp_configuration():
    token=issue_local_session()
    return JSONResponse({'mcpServers':{'neuroloop':{'url':'http://127.0.0.1:8010/mcp/',
        'headers':{'Authorization':'Bearer '+token}}}},
        headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="neuroloop-mcp.json"'})

@app.post('/api/connections/mcp/test')
async def test_mcp_connection():
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with asyncio.timeout(12):
        async with httpx.AsyncClient(headers={'Authorization':'Bearer '+issue_local_session()}) as client:
            async with streamable_http_client('http://127.0.0.1:8010/mcp/',http_client=client) as streams:
                async with ClientSession(streams[0],streams[1]) as session:
                    initialized=await session.initialize()
                    result=await session.list_tools()
                    return {'status':'connected','server':initialized.serverInfo.name,
                            'tools':[tool.name for tool in result.tools],
                            'schemas':[{'name':tool.name,'description':tool.description,'inputSchema':tool.inputSchema} for tool in result.tools]}

@app.post('/api/compare')
def compare(body: CompareRequest):
    with Session() as db: rows=[db.get(Evaluation,x) for x in body.evaluation_ids]
    if any(x is None for x in rows): raise HTTPException(404,'Evaluation not found')
    if len({x.profile for x in rows})!=1: raise HTTPException(409,'Cannot compare different evaluator profiles')
    if any(not x.prediction_path or not Path(x.prediction_path).is_file() for x in rows):
        raise HTTPException(409,'Comparison requires available cortical arrays for every selected evaluation')
    arrays=[np.load(x.prediction_path,allow_pickle=False,mmap_mode='r') for x in rows]
    return {'metric':METRIC,'evaluation_ids':body.evaluation_ids,'matrix':[[similarity(a,b) for b in arrays] for a in arrays],'meaning':'Predicted cortical-pattern similarity, not human preference.'}

@app.get('/api/runs/{identity}/export')
def export(identity: str):
    result=services.get_run(identity)
    if result['status'] in {'queued','running'}: raise HTTPException(409,'Wait for completion or cancel at a safe checkpoint before exporting')
    best_id=result['result'].get('best_asset_id')
    if not best_id: raise HTTPException(409,'No completed artifact is available')
    source=asset_file(best_id);archive=s.data/'exports'/f'{identity}-{uid()}.zip'
    evaluation_ids=set()
    for key,value in result['result'].items():
        if key.endswith('_evaluation_id') and isinstance(value,str): evaluation_ids.add(value)
        if key.endswith('_evaluation_ids') and isinstance(value,list): evaluation_ids.update(x for x in value if isinstance(x,str))
    for experiment in result.get('experiments',[]):
        recorded=experiment.get('evidence',{}).get('evaluation_id')
        if recorded: evaluation_ids.add(recorded)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.write(source,'selected-creative'+source.suffix)
        z.writestr('evidence.json',json.dumps(result,indent=2))
        with Session() as db:
            for evaluation_id in sorted(evaluation_ids):
                row=db.get(Evaluation,evaluation_id)
                if row is None: continue
                z.writestr(f'evaluations/{evaluation_id}/evidence.json',json.dumps(as_dict(row,('prediction_path',)),indent=2))
                if row.prediction_path:
                    tensor_path=Path(row.prediction_path).resolve()
                    if tensor_path.is_relative_to(s.data.resolve()) and tensor_path.is_file():
                        z.write(tensor_path,f'evaluations/{evaluation_id}/prediction.npy')
        provenance=s.data/'geometry/provenance.json'
        if provenance.is_file(): z.write(provenance,'geometry-provenance.json')
        z.writestr('READ-ME.txt','NeuroLoop evidence export. Cortical predictions and reference similarities are model outputs, not human measurements, purchase probabilities, or emotion diagnoses. Original model licenses still apply.\n')
    from starlette.background import BackgroundTask
    return FileResponse(archive,media_type='application/zip',filename=f'neuroloop-{identity[:8]}.zip',background=BackgroundTask(archive.unlink,missing_ok=True))

app.mount('/mcp',mcp.streamable_http_app())
