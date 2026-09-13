"""Export real outcome tables and optionally publish a verified Weave/W&B snapshot."""
from pathlib import Path
import argparse
import json
import os
from neuroloop_app.config import Settings
from neuroloop_app.db import Store
from neuroloop_app.outcome_telemetry import snapshot, TABLE_NAMES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--refresh', action='store_true', help='Refresh the existing dashboard run even for an unchanged snapshot')
    parser.add_argument('--output', default='artifacts/telemetry')
    args = parser.parse_args()
    settings = Settings()
    store = Store(settings); store.initialize()
    data = snapshot(store)
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    (root / 'outcome-snapshot.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps({'snapshot_sha256':data['snapshot_sha256'], 'metrics':data['metrics']}))
    if not args.publish:
        return
    receipt_path = root / ('published-' + data['snapshot_sha256'] + '.json')
    if receipt_path.exists() and not args.refresh:
        print(receipt_path.read_text()); return
    from neuroloop_app.notebook_telemetry import publish_snapshot
    previous = root / 'weave-snapshot-receipt.json'
    receipt = json.loads(previous.read_text()) if previous.exists() else {}
    if receipt.get('snapshot_sha256') != data['snapshot_sha256'] or receipt.get('status') != 'VERIFIED':
        receipt = publish_snapshot(settings, data, root)
    import wandb
    os.environ.setdefault('WANDB_API_KEY', settings.wandb_api_key.get_secret_value())
    run = wandb.init(project=settings.wandb_project.split('/')[-1], entity=settings.wandb_project.split('/')[0],
        id='neuroloop-outcomes', resume='allow', job_type='outcome-telemetry',
        settings=wandb.Settings(x_disable_stats=True),
        group='product-outcomes', name='NeuroLoop · execution and evidence',
        config={'schema_version':data['schema_version'], 'snapshot_sha256':data['snapshot_sha256'], 'source':'persisted-records'})
    try:
        run.config.update({'schema_version': data['schema_version'], 'snapshot_sha256': data['snapshot_sha256']}, allow_val_change=True)
        logged = {k:v for k,v in data['metrics'].items() if isinstance(v,(int,float))}
        for name in TABLE_NAMES:
            if data[name]:
                columns = list(dict.fromkeys(k for row in data[name] for k in row))
                logged[name] = wandb.Table(columns=columns, data=[[
                    json.dumps(row.get(k), sort_keys=True) if isinstance(row.get(k), (dict, list)) else row.get(k)
                    for k in columns] for row in data[name]])
        logged['charts/campaign_funnel'] = wandb.plot.bar(logged['funnel'], 'stage', 'completed_runs', title='Actual campaign funnel')
        logged['charts/execution_readiness'] = wandb.plot.bar(logged['readiness_stages'], 'stage', 'verified_runs', title='Execution evidence: registered is not verified')
        if 'stages' in logged:
            logged['charts/p95_stage_latency'] = wandb.plot.bar(logged['stages'], 'stage', 'p95_seconds', title='Recorded p95 attempt latency (seconds)')
        if 'failures' in logged:
            logged['charts/failure_codes'] = wandb.plot.bar(logged['failures'], 'error_code', 'attempts', title='Actual failures, including retries')
        run.log(logged)
        run.summary['weave_snapshot_url'] = receipt['url']
        run.summary['unknown_cost_policy'] = 'Unavailable, never zero'
        run.summary['human_outcome_policy'] = 'Only explicit accept / accept_after_edit feedback'
        receipt['wandb_run_url'] = run.url
        receipt['wandb_run_id'] = run.id
    except BaseException:
        run.finish(exit_code=1)
        raise
    else:
        run.finish()
    remote = wandb.Api().run(settings.wandb_project + '/' + receipt['wandb_run_id'])
    if remote.summary.get('optimization_runs_started') != data['metrics']['optimization_runs_started']:
        raise RuntimeError('W&B did not confirm outcome metrics')
    receipt['wandb_status'] = 'VERIFIED'
    receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
