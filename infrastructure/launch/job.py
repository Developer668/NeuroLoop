"""NeuroLoop Launch contract v1. Executed only by the allowlisted local runner.

The runner invokes the installed scripts/launch_entry.py. This artifact is the
versioned public job contract, not a copy of model weights or workspace media.
"""
if __name__=='__main__':
    raise SystemExit('Use the NeuroLoop local Launch agent. Generic agents cannot execute this contract.')
