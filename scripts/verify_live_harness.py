"""Exercise real HTTP, media, GLM, TypeSafe and Weave; never substitute models.

Default verifies provider/control-plane stages. --full-loop additionally requires
the configured real generator and evaluators to complete the actual search.
Receipts live in an isolated directory, separate from user campaigns.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import threading
import time

import httpx
import uvicorn

from neuroloop_app.api import create_app
from neuroloop_app.config import Settings
from neuroloop_app.domain import CampaignSpec, BrandSpec, RunConfig, StartRun, uid
from neuroloop_app.model_adapters import configure_models
from neuroloop_app.notebook import ModelRegistry, NotebookWorker, LocalAsset, EvaluationContext
from neuroloop_app.telemetry import WeaveExporter
from neuroloop_app.vision_adapter import VisionAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--full-loop', action='store_true')
    args = parser.parse_args()
    source = args.media.resolve(strict=True)
    root = Path('data/verification') / ('live-harness-' + uid())
    root.mkdir(parents=True)
    settings = Settings(data_dir=root.resolve(), database_url='', environment='development')
    for name in ('wandb_api_key', 'typesafe_api_key', 'worker_token', 'operator_token'):
        if not getattr(settings, name).get_secret_value():
            raise RuntimeError(f'{name} is not configured')
    app = create_app(settings)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    report = {'full_loop_verified': False, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError('Verification API failed to start')
            time.sleep(.1)
        with httpx.Client(base_url=url, headers={'Authorization': 'Bearer ' + settings.operator_token.get_secret_value()}, timeout=60) as api:
            def post(path, **kwargs):
                response = api.post(path, **kwargs)
                response.raise_for_status()
                return response.json()
            spec = CampaignSpec(title='NeuroLoop live harness verification',
                brief='Create a clean brand presentation grounded in the supplied artwork. Preserve the reference identity and do not invent claims.',
                brand=BrandSpec(name='NeuroLoop', product_description='Creative optimization software; use only the supplied visual identity.'),
                media_kind='video' if source.suffix.lower() in {'.mp4', '.mov', '.webm'} else 'image', aspect_ratio='1:1')
            campaign = post('/api/v2/campaigns', json=spec.model_dump())
            with source.open('rb') as media:
                asset = post(f'/api/v2/campaigns/{campaign["id"]}/assets', files={'file': (source.name, media)})
            local = LocalAsset(asset['id'], source, asset['kind'], asset['mime'], asset['sha256'], asset['details'])
            vision = VisionAdapter(settings)(EvaluationContext(uid(), 'source-inspection', spec.model_dump(), local,
                [local], ['product_identity', 'approved_claims_only', 'no_prohibited_claims'], root, lambda: False)).result
            (root / 'vision.json').write_text(vision.model_dump_json(indent=2), encoding='utf-8')
            if vision.status != 'SUCCEEDED':
                raise RuntimeError('Live vision did not succeed')
            report['vision_receipt'] = vision.observations['provider_receipt']
            cfg = RunConfig(initial_candidates=1, beam_width=1, branch_factor=1, max_rounds=2,
                required_evaluators=['vision', 'tsam', 'tribe'] if args.full_loop and spec.media_kind == 'video' else ['vision'],
                optional_evaluators=[], max_model_calls=20)
            run = post(f'/api/v2/campaigns/{campaign["id"]}/runs', json=StartRun(config=cfg, reference_asset_ids=[asset['id']]).model_dump(),
                       headers={'Idempotency-Key': uid()})
            registry = configure_models(ModelRegistry(), settings)
            worker = NotebookWorker(registry, settings, api_url=url, cache_dir=root / 'worker')
            try:
                for _ in range(25 if args.full_loop else 2):
                    if not worker.run_once():
                        break
                    snapshot = api.get(f'/api/v2/runs/{run["id"]}').json()
                    print(json.dumps(worker.last_status), flush=True)
                    if snapshot['run']['state'] in {'READY_FOR_REVIEW', 'NEEDS_ATTENTION', 'FAILED', 'CANCELLED'}:
                        break
                snapshot = api.get(f'/api/v2/runs/{run["id"]}').json()
                (root / 'run.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
                report['run_id'] = run['id']
                report['jobs'] = [{'kind': j['kind'], 'status': j['status']} for j in snapshot['jobs']]
                report['control_plane_verified'] = all(any(j['kind'] == kind and j['status'] == 'SUCCEEDED' for j in snapshot['jobs']) for kind in ['PLAN', 'REVIEW_PLAN'])
                report['capabilities'] = registry.describe()
                report['full_loop_verified'] = (args.full_loop and snapshot['run']['state'] == 'READY_FOR_REVIEW'
                    and any(j['kind'] == 'DECIDE' and j['status'] == 'SUCCEEDED' for j in snapshot['jobs'])
                    and all(j['status'] == 'SUCCEEDED' for j in snapshot['jobs']))
                if not report['full_loop_verified']:
                    post(f'/api/v2/runs/{run["id"]}/cancel')
                exporter = WeaveExporter(app.state.engine.store)
                deadline = time.monotonic() + 45
                while True:
                    report['weave_export'] = exporter.drain(30)
                    final = api.get(f'/api/v2/runs/{run["id"]}').json()
                    if all(t['status'] == 'DELIVERED' for t in final['traces']) or time.monotonic() >= deadline:
                        break
                    time.sleep(2)
                report['trace_urls'] = [t['url'] for t in final['traces'] if t['status'] == 'DELIVERED']
                report['weave_verified'] = bool(final['traces']) and all(t['status'] == 'DELIVERED' for t in final['traces'])
            finally:
                worker.stop()
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        (root / 'receipt.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Receipt:', (root / 'receipt.json').resolve())
    print(json.dumps({k: report.get(k) for k in ['control_plane_verified', 'weave_verified', 'full_loop_verified', 'trace_urls']}, indent=2))
    return 0 if report.get('control_plane_verified') and report.get('weave_verified') and (not args.full_loop or report['full_loop_verified']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
