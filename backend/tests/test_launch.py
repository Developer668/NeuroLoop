from copy import deepcopy
import pytest
from neuroloop.launch_contract import validate_spec

MANIFEST={'job':'entity/project/bounded:v0','entity':'entity','project':'project'}
SPEC={**MANIFEST,'resource':'local-process','docker':{},'git':{},'resource_args':{'local-process':{}},'overrides':{'run_config':{'proposal_id':'approved-id'}}}

def approved(identity):
    assert identity=='approved-id'
    return {'status':'approved'}

def test_installed_approved_job_accepted():
    assert validate_spec(SPEC,MANIFEST,approved)['status']=='approved'

@pytest.mark.parametrize('key,value',[
    ('job','entity/project/bounded:latest'),('resource','kubernetes'),('entity','outsider'),
    ('entry_point',['cmd','/c','echo nope']),('docker',{'docker_image':'unreviewed'}),
    ('git',{'uri':'remote'}),('resource_args',{'local-process':{'env':{'PYTHONPATH':'unreviewed'}}}),
    ('overrides',{'run_config':{'proposal_id':'approved-id','budget':999}}),
    ('overrides',{'run_config':{'proposal_id':'approved-id'},'files':{'job.py':'unreviewed'}}),
])
def test_remote_overrides_cannot_execute(key,value):
    spec=deepcopy(SPEC);spec[key]=value
    with pytest.raises(ValueError):validate_spec(spec,MANIFEST,approved)

def test_unapproved_proposal_rejected():
    with pytest.raises(ValueError,match='approved'):
        validate_spec(SPEC,MANIFEST,lambda _: {'status':'proposed'})

def test_one_shot_cannot_claim_another_approved_proposal():
    with pytest.raises(ValueError,match='selected proposal'):
        validate_spec(SPEC,MANIFEST,approved,expected_proposal='different-id')
    assert validate_spec(SPEC,MANIFEST,approved,expected_proposal='approved-id')['status']=='approved'
