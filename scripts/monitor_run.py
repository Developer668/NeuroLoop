"""Record bounded read-only GPU/RAM samples for a real existing proposal run."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.hardware import hardware_status
from neuroloop.agent_bridge import get_proposal
from neuroloop.services import get_run
from neuroloop.db import now
from neuroloop.persistence import atomic_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('proposal_id');a=p.parse_args()
    out=ROOT/'data/verification/release'/('stability-'+a.proposal_id+'.json')
    report={'proposal_id':a.proposal_id,'started_at':now(),'samples':[],'limit':'A bounded run cannot establish the cause or resolution of a kernel graphics crash.'}
    deadline=time.monotonic()+1020
    while time.monotonic()<deadline:
        proposal=get_proposal(a.proposal_id)
        run=get_run(proposal['run_id']) if proposal['run_id'] else None
        report['samples'].append({'at':now(),'hardware':hardware_status(),'run_status':run['status'] if run else 'not_received','stage':run['stage'] if run else 'Awaiting Launch'})
        if run and run['status'] not in ('queued','running'):
            report['run_id']=run['id'];report['final_status']=run['status'];atomic_json(out,report);print(json.dumps({'run_id':run['id'],'status':run['status'],'samples':len(report['samples'])}));return
        atomic_json(out,report);time.sleep(5)
    report['monitor_status']='timeout';atomic_json(out,report);raise SystemExit('Monitoring deadline reached')

if __name__=='__main__':main()
