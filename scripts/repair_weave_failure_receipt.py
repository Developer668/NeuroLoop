"""Publish a linked classification audit for one recorded failure; preserve its original trace."""
from pathlib import Path
import argparse, json, sys
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.config import settings
settings()
from neuroloop.db import engine, now
from neuroloop.delivery import recorded_exception
from neuroloop.telemetry import client
from neuroloop.persistence import atomic_json
from sqlalchemy import text

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt_id')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with engine.connect() as db:
        row=db.execute(text('SELECT * FROM external_receipts WHERE id=:id'),{'id':args.receipt_id}).mappings().one()
    payload=json.loads(row['payload'])
    if row['status']!='delivered' or not recorded_exception(payload):
        raise ValueError('Only a delivered receipt containing an actual local failure can be repaired')
    report={'receipt_id':args.receipt_id,'run_id':payload.get('run_id'),'original_url':row['url'],'scope':'classification repair, not a new model run','applied':False}
    if args.apply:
        import uuid
        from neuroloop.delivery import enqueue, drain, receipts
        audit_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'neuroloop/failure-classification/v1/'+args.receipt_id))
        enqueue('neuroloop.failure_classification_audit', {'run_id':payload.get('run_id'), 'parent_receipt_id':args.receipt_id, 'exception_type':payload.get('exception_type') or 'RecordedFailure', 'status':'failed'},audit_id)
        drain(limit=20)
        result=next(r for r in receipts(limit=100) if r['id']==audit_id)
        report.update(audit_receipt_id=audit_id,applied=result['status']=='delivered',remote_status=result['status'],url=result.get('url'),verified_at=now(),original_preserved=True)
        atomic_json(ROOT/'artifacts/weave-review'/f'repair-{args.receipt_id}.json',report)
        if not report['applied']: raise RuntimeError('Audit export not delivered; inspect the durable outbox')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
