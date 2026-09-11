"""The only remote job accepted by this local installation."""
def validate_spec(spec, manifest, get_proposal):
    permitted={'job','resource','entity','project','overrides','resource_args','docker','git','author','_wandb_job_collection_id'}
    if set(spec)-permitted:
        raise ValueError('Unknown Launch fields are prohibited')
    if (spec.get('job')!=manifest['job'] or spec.get('resource')!='local-process'
            or spec.get('entity')!=manifest['entity'] or spec.get('project')!=manifest['project']):
        raise ValueError('Only the installed NeuroLoop job and local target are allowed')
    if spec.get('docker') or spec.get('git') or spec.get('resource_args',{}) not in ({},{'local-process':{}}):
        raise ValueError('Executable and resource overrides are prohibited')
    overrides=spec.get('overrides',{})
    if set(overrides)!={'run_config'} or set(overrides['run_config'])!={'proposal_id'}:
        raise ValueError('Only a proposal_id may be supplied by Launch')
    proposal=get_proposal(overrides['run_config']['proposal_id'])
    if proposal['status'] not in {'approved','queued'}:
        raise ValueError('This proposal has not been explicitly approved locally')
    return proposal
