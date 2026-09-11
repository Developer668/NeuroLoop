"""Optional, explicit Weave tracing. Never uploads source media, tensors, prompts, or secrets."""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging,os,threading,time
from .config import settings
log=logging.getLogger(__name__)
_client=None
_lock=threading.Lock()
_failed_until=0.0
_parent=ContextVar('neuroloop_weave_parent',default=None)

def client():
    global _client,_failed_until
    if not settings().weave_enabled or not os.getenv('WANDB_API_KEY') or time.monotonic()<_failed_until:return None
    with _lock:
        if _client is not None:return _client
        try:
            import weave
            _client=weave.init(os.getenv('WANDB_PROJECT','neuroloop'),attributes={'application':'neuroloop','data_policy':'metadata-only'})
            return _client
        except Exception as exc:
            _failed_until=time.monotonic()+60
            log.warning('Weave tracing unavailable: %s',type(exc).__name__)
            return None

@contextmanager
def span(name: str, inputs: dict):
    import uuid
    from .delivery import enqueue
    from .db import now
    identity=str(uuid.uuid4()); parent=_parent.get()
    token=_parent.set(identity); result={}; started=time.monotonic(); started_at=now()
    try:
        yield result
    except BaseException as exc:
        result['exception_type']=type(exc).__name__
        raise
    finally:
        _parent.reset(token)
        try:
            enqueue(name,{**inputs,**result,'parent_receipt_id':parent,'started_at':started_at,'ended_at':now(),'compute_seconds':result.get('compute_seconds',time.monotonic()-started)},identity)
        except Exception as exc:
            log.error('Cannot persist trace receipt: %s',type(exc).__name__)

def traced(name:str):
    def decorate(function):
        @wraps(function)
        def wrapped(*args,**kwargs):
            metadata={'run_id':args[0] if args and isinstance(args[0],str) else kwargs.get('identity')}
            if len(args)>1 and hasattr(args[1],'id'):metadata['asset_id']=args[1].id
            if name=='neuroloop.render' and len(args)>4:metadata['operator']=args[4]
            with span(name,metadata) as evidence:
                value=function(*args,**kwargs)
                if hasattr(value,'id'):evidence['record_id']=value.id
                if hasattr(value,'profile'):evidence['profile']=value.profile
                if hasattr(value,'duration_seconds'):evidence['compute_seconds']=value.duration_seconds
                if isinstance(value,dict):
                    for key in ['run_id','status','evaluations_used','compute_seconds','decision','gain']:
                        if key in value:evidence[key]=value[key]
                return value
        return wrapped
    return decorate
