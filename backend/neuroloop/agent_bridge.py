"""Versioned, reviewable proposal bridge; external agents cannot supply executable code."""
import hashlib,json,uuid
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from sqlalchemy import text
from .db import engine,now
from .schemas import RunCreate
from . import services

class Proposal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version: Literal[1]=1
    source: Literal['ARIA','W&B MCP','local agent']
    base_run_id: str
    operator: str
    hypothesis: str=Field(min_length=1,max_length=1000)

def propose(body: Proposal):
    base=services.get_run(body.base_run_id)
    request=RunCreate.model_validate(base['config']['request'])
    if base['mode']!='optimize' or base['status'] not in {'completed','failed'}:
        raise services.DomainError('A completed or failed controlled optimization is required as context')
    if body.operator not in request.operators:
        raise services.DomainError('Proposal operator is outside the original permitted set')
    request.operators=[body.operator]
    request.max_evaluations=min(4,request.max_evaluations)
    request.max_seconds=min(900,request.max_seconds)
    request.hypothesis=body.hypothesis
    identity=str(uuid.uuid4())
    specification={'version':1,'proposal':body.model_dump(),'request':request.model_dump(),'objective':base['config']['objective'],'project_snapshot':base['config']['project_snapshot']}
    encoded=json.dumps(specification,sort_keys=True,separators=(',',':'))
    with engine.begin() as db:
        db.execute(text('INSERT INTO agent_proposals(id,version,source,specification,created_at) VALUES (:id,1,:source,:spec,:t)'),{'id':identity,'source':body.source,'spec':encoded,'t':now()})
    return get_proposal(identity)

def get_proposal(identity):
    with engine.connect() as db:
        row=db.execute(text('SELECT * FROM agent_proposals WHERE id=:id'),{'id':identity}).mappings().first()
    if not row: raise services.DomainError('Agent proposal not found')
    result=dict(row);encoded=result.pop('specification')
    return {**result,'specification':json.loads(encoded),'approval_digest':hashlib.sha256(encoded.encode()).hexdigest()}

def execute(identity,expected_digest):
    record=get_proposal(identity)
    if expected_digest!=record['approval_digest']:
        raise services.DomainError('Approval does not match the reviewed proposal')
    if record['run_id']: return services.get_run(record['run_id'])
    spec=record['specification']
    # The frozen base contract is invalidated if the project has since changed.
    from .db import Session,Project,as_dict
    with Session() as db:
        project=db.get(Project,spec['request']['project_id'])
        if not project or as_dict(project)!=spec['project_snapshot']:
            raise services.DomainError('Project changed since the base run; create a fresh local experiment first')
    result=services.create_run(RunCreate.model_validate(spec['request']),'agent-proposal/'+identity,expected_project=spec['project_snapshot'])
    with engine.begin() as db:
        db.execute(text("UPDATE agent_proposals SET status='queued',run_id=:run WHERE id=:id"),{'id':identity,'run':result['id']})
    return result
