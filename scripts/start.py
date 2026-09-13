"""Run new-project CPU API + frontend; no notebook, GPU or old V1 processes."""
from pathlib import Path
import os, subprocess, sys, signal, time
from dotenv import load_dotenv
root=Path(__file__).resolve().parents[1]
load_dotenv(root/'.env',override=False)
api_port=os.environ.get('NEUROLOOP_API_PORT','8010'); web_port=os.environ.get('NEUROLOOP_WEB_PORT','3010')
python=sys.executable
import socket
for port in (api_port,web_port):
    with socket.socket() as probe:
        try: probe.bind(('127.0.0.1',int(port)))
        except OSError: raise SystemExit(f'Port {port} is occupied. Existing processes are not stopped.')
children=[]
vision_child=None
vision_restart_at=0
try:
    children.append(subprocess.Popen([python,'-m','uvicorn','neuroloop_app.api:create_app','--factory','--host','127.0.0.1','--port',api_port],cwd=root))
    cmd=['node',str(root/'frontend/node_modules/next/dist/bin/next'),'dev','--hostname','127.0.0.1','--port',web_port]
    children.append(subprocess.Popen(cmd,cwd=root/'frontend'))
    # CPU vision/ASR is optional. Its idle timeout or failure must not take the
    # website down; the supervisor restarts it with a bounded delay.
    while all(p.poll() is None for p in children):
        if os.environ.get('NEUROLOOP_AUDIO_TRANSCRIPTION_MODEL_PATH') and time.monotonic() >= vision_restart_at:
            if vision_child is None or vision_child.poll() is not None:
                vision_child=subprocess.Popen([python,str(root/'scripts/vision_worker.py')],cwd=root)
                vision_restart_at=time.monotonic()+30
        time.sleep(1)
finally:
    if vision_child is not None: children.append(vision_child)
    for p in children:
        if p.poll() is None:
            if os.name=='nt': subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:p.terminate()
