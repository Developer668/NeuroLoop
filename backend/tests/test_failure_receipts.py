from neuroloop.delivery import recorded_exception

def test_failure_is_visible_without_private_exception_text():
    error=recorded_exception({'exception_type':'RuntimeError','error':'private-media-path and token'})
    assert isinstance(error,RuntimeError)
    assert 'private' not in str(error) and 'token' not in str(error)

def test_success_and_deliberate_cancel_are_not_exceptions():
    assert recorded_exception({'status':'completed'}) is None
    assert recorded_exception({'status':'cancelled'}) is None
    assert recorded_exception({'status':'failed'}) is not None


def test_failed_receipt_requires_remote_exception(client,monkeypatch):
    import uuid
    from types import SimpleNamespace
    from sqlalchemy import text
    from neuroloop.config import settings
    from neuroloop.db import engine
    from neuroloop.delivery import enqueue,drain,receipts
    monkeypatch.setattr(settings(),'weave_enabled',True)
    monkeypatch.setenv('WANDB_PROJECT','entity/project')
    identity=str(uuid.uuid4())
    enqueue('test.failure',{'run_id':'local','exception_type':'RuntimeError'},identity)
    class Transport:
        exception=None
        def create_call(self,**kwargs):return SimpleNamespace(id=kwargs['_call_id_override'])
        def finish_call(self,call,**kwargs):
            assert isinstance(kwargs['exception'],RuntimeError)
            assert kwargs['output']['local_outcome']=='failed'
        def flush(self):pass
        def get_call(self,identity):return SimpleNamespace(id=identity,ended_at='done',exception=self.exception)
    transport=Transport()
    assert drain(connection=transport)==0
    assert next(r for r in receipts() if r['id']==identity)['status']=='retry'
    with engine.begin() as db:db.execute(text('UPDATE external_receipts SET next_attempt=0 WHERE id=:id'),{'id':identity})
    transport.exception='Recorded local operation failed'
    assert drain(connection=transport)==1
    assert next(r for r in receipts() if r['id']==identity)['status']=='delivered'
