"""Durable metadata-only Weave outbox. Delivery requires a remote read receipt."""
from __future__ import annotations
import json, os, time, uuid
from datetime import datetime
from sqlalchemy import text
from filelock import FileLock, Timeout
from .db import engine, now
from .config import settings

FIELDS = {'run_id','asset_id','record_id','profile','compute_seconds','status','evaluations_used','decision','gain','operator','evaluation_id','experiment_id','metric','exception_type','parent_receipt_id','started_at','ended_at'}

def recorded_exception(payload):
    """Project a recorded local failure into Weave without sending error text."""
    if payload.get('exception_type') or payload.get('status') == 'failed':
        return RuntimeError('Recorded local operation failed; inspect the local execution log for details.')
    return None

def enqueue(name: str, payload: dict, identity: str | None = None) -> str | None:
    if not settings().weave_enabled:
        return None
    clean = {k:v for k,v in payload.items() if k in FIELDS and isinstance(v,(str,int,float,bool,type(None)))}
    identity = identity or str(uuid.uuid4())
    with engine.begin() as connection:
        if not connection.execute(text('SELECT id FROM external_receipts WHERE id=:id'),{'id':identity}).first():
            connection.execute(text('INSERT INTO external_receipts(id,name,payload,created_at) VALUES (:id,:name,:payload,:created)'),dict(id=identity,name=name,payload=json.dumps(clean,allow_nan=False),created=now()))
    return identity

def receipts(limit=100):
    with engine.connect() as connection:
        rows=connection.execute(text('SELECT id,name,status,attempts,external_id,url,error,created_at,delivered_at FROM external_receipts ORDER BY created_at DESC LIMIT :n'),{'n':min(limit,500)})
        return [dict(row._mapping) for row in rows]

def drain(limit=5, connection=None):
    if not settings().weave_enabled or (connection is None and not os.getenv('WANDB_API_KEY')):
        return 0
    from .telemetry import client
    completed=0
    try:
        with FileLock(str(settings().data/'weave-delivery.lock'),timeout=0):
            connection=connection or client()
            if connection is None: return 0
            with engine.connect() as db:
                pending=[dict(row._mapping) for row in db.execute(text("SELECT * FROM external_receipts WHERE status IN ('pending','retry') AND next_attempt<=:t AND attempts<8 ORDER BY created_at LIMIT :n"),{'t':time.time(),'n':limit})]
            for row in pending:
                attempts=row['attempts']+1
                with engine.begin() as db:
                    db.execute(text('UPDATE external_receipts SET attempts=:a,next_attempt=:t WHERE id=:id'),{'a':attempts,'t':time.time()+min(3600,30*2**attempts),'id':row['id']})
                try:
                    # Same call ID on retry: crashes cannot silently create a new logical event.
                    payload=json.loads(row['payload'])
                    call=connection.create_call(op=row['name'],inputs=payload,use_stack=False,_call_id_override=row['id'],started_at=datetime.fromisoformat(payload.get('started_at',row['created_at'])),attributes={'application':'neuroloop','data_policy':'metadata-only','receipt_id':row['id']})
                    failure=recorded_exception(payload)
                    connection.finish_call(call,output={'locally_recorded':True,'local_outcome':'failed' if failure else payload.get('status','recorded')},exception=failure,ended_at=datetime.fromisoformat(payload.get('ended_at',row['created_at'])))
                    connection.flush()
                    remote=connection.get_call(row['id'])
                    if getattr(remote,'id',None)!=row['id'] or getattr(remote,'ended_at',None) is None:
                        raise RuntimeError('Remote receipt is not complete')
                    if failure and not getattr(remote,'exception',None):
                        raise RuntimeError('Remote receipt did not preserve the local failure')
                    project=os.environ['WANDB_PROJECT']
                    url=f'https://wandb.ai/{project}/weave/calls/{row["id"]}'
                    with engine.begin() as db:
                        db.execute(text("UPDATE external_receipts SET status='delivered',external_id=:id,url=:url,error=NULL,delivered_at=:t WHERE id=:id"),{'id':row['id'],'url':url,'t':now()})
                    completed+=1
                except Exception as exc:
                    # Exception text may contain credentials or request content. Retain safe type only.
                    with engine.begin() as db:
                        db.execute(text('UPDATE external_receipts SET status=:s,error=:e WHERE id=:id'),{'s':'failed' if attempts>=8 else 'retry','e':type(exc).__name__,'id':row['id']})
    except Timeout:
        pass
    return completed
