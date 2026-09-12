"""Create NEW local secrets without reading, copying or changing NeuroLoopV1."""
from pathlib import Path
import argparse
import os
import secrets
import socket

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--api-port',type=int,default=8010)
parser.add_argument('--web-port',type=int,default=3010)
args=parser.parse_args()
for port in (args.api_port,args.web_port):
    with socket.socket() as s:
        try:s.bind(('127.0.0.1',port))
        except OSError:raise SystemExit(f'Port {port} is occupied. Choose another port; existing applications are never stopped.')
path=ROOT/'.env'
if path.exists():
    raise SystemExit('Existing .env preserved. Change configuration manually; secrets will not be overwritten.')
keys={name:secrets.token_urlsafe(48) for name in ('OPERATOR_TOKEN','AGENT_TOKEN','WORKER_TOKEN','LOCAL_BOOTSTRAP_TOKEN','SIGNING_KEY')}
values={**{'NEUROLOOP_'+name:value for name,value in keys.items()},
    'NEUROLOOP_PUBLIC_API_URL':f'http://127.0.0.1:{args.api_port}',
    'NEUROLOOP_FRONTEND_ORIGIN':f'http://localhost:{args.web_port}',
    'NEUROLOOP_API_PORT':str(args.api_port),'NEUROLOOP_WEB_PORT':str(args.web_port),
    'NEUROLOOP_INFERENCE_MODEL':'','WANDB_API_KEY':'','WANDB_PROJECT':'','TYPESAFE_API_KEY':'',
    'NEUROLOOP_WEAVE_ENABLED':'false','NEUROLOOP_PROVIDER':'local','NEUROLOOP_PROVIDER_WORKLOAD_APPROVED':'false',
    'META_ACCESS_TOKEN':'','NEUROLOOP_META_GRAPH_VERSION':'',
    'POSTGRES_PASSWORD':secrets.token_urlsafe(32),'MINIO_ROOT_USER':'neuroloop','MINIO_ROOT_PASSWORD':secrets.token_urlsafe(32)}
with path.open('x',encoding='utf-8') as f:
    f.write('\n'.join(f'{k}={v}' for k,v in values.items())+'\n')
os.chmod(path,0o600)
front=ROOT/'frontend/.env.local'
if front.exists():
    raise SystemExit('Backend secrets created, existing frontend/.env.local preserved. Set its internal API URL and bootstrap key manually.')
with front.open('x',encoding='utf-8') as f:
    f.write(f'NEUROLOOP_INTERNAL_API=http://127.0.0.1:{args.api_port}\nNEUROLOOP_LOCAL_BOOTSTRAP_TOKEN={keys["LOCAL_BOOTSTRAP_TOKEN"]}\n')
os.chmod(front,0o600)
print(f'Created ignored server/frontend configuration. Secrets are NOT printed. API port {args.api_port}; web port {args.web_port}.')
print('Models and paid sponsor APIs remain unconfigured. Add their credentials only through .env or notebook secrets.')
