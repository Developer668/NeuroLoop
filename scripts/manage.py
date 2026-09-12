"""Start/stop the local application without terminating unrelated processes.

The supervisor owns its API, web, research and model-worker child processes.
Stop requests are handled by that supervisor. Services bind to loopback only.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import webbrowser
from pathlib import Path
from windows_job import OwnedJob

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
STATE = DATA / 'services.json'
STOP = DATA / 'stop-services.request'
PORTS = {'api': 8010, 'web': 3010, 'research': 2718}


def runtime_python(name: str) -> Path:
    executable = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    return ROOT / '.runtimes' / name / executable


def mac_mps_override_enabled() -> bool:
    return sys.platform == 'darwin' and os.getenv('NEUROLOOP_ALLOW_MPS_INFERENCE', '').lower() in {'1', 'true', 'yes'}


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.4):
            return True
    except OSError:
        return False


def get_status() -> dict:
    recorded = {}
    if STATE.exists():
        try:
            recorded = json.loads(STATE.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pass
    return {'services': {name: {'port': port, 'listening': port_open(port)} for name, port in PORTS.items()}, 'supervisor': recorded}


def endpoint_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def stop_children(children: dict) -> None:
    deadline = time.monotonic() + 12
    if os.name != 'nt':
        import psutil
        # Terminate descendants before their service parent is re-parented.
        for process in children.values():
            if process.poll() is not None:
                continue
            try:
                descendants = psutil.Process(process.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                descendants = []
            for child in reversed(descendants):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
    for process in children.values():
        if process.poll() is None:
            process.terminate()
    for process in children.values():
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def serve(open_browser: bool, model_runtime: str = 'model') -> None:
    executable = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    python = ROOT / '.venv' / executable
    model_python = ROOT / 'tribev2-balanced-qv-local/.venv' / executable
    active = ROOT / '.runtimes/active.json'
    if active.exists() or os.getenv('NEUROLOOP_STAGED_RUNTIME') == 'true' or runtime_python('app').exists():
        python = runtime_python('app')
        model_python = runtime_python(model_runtime)
    node = shutil.which('node')
    next_cli = ROOT / 'frontend/scripts/start-server.mjs'
    if not python.exists() or not model_python.exists() or not node or not next_cli.exists():
        raise RuntimeError('A required local runtime is missing. Follow README.md setup instructions.')
    if not (ROOT / 'frontend/.next/BUILD_ID').exists():
        raise RuntimeError('Build the web application first: npm.cmd run build in frontend.')
    occupied = [f'{name}:{port}' for name, port in PORTS.items() if port_open(port)]
    if occupied:
        raise RuntimeError('Ports already in use: ' + ', '.join(occupied) + '. No process was stopped. Existing services may already be running.')
    DATA.mkdir(exist_ok=True)
    (DATA / 'logs').mkdir(exist_ok=True)
    STOP.unlink(missing_ok=True)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT / 'backend')
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONUTF8'] = '1'
    env['NEUROLOOP_RESEARCH_ENABLED'] = 'true'
    env['NEUROLOOP_MODEL_PYTHON'] = str(model_python)
    commands = {
        'api': ([str(python), '-m', 'uvicorn', 'neuroloop.api:app', '--host', '127.0.0.1', '--port', '8010', '--no-access-log'], ROOT),
        'worker': ([str(model_python), '-u', str(ROOT / 'scripts/run_worker.py')], ROOT),
        'web': ([node, str(next_cli)], ROOT / 'frontend'),
        'research': ([str(python), '-m', 'marimo', 'run', str(ROOT / 'research/lab.py'), '--host', '127.0.0.1', '--port', '2718', '--no-token'], ROOT),
    }
    quarantined=(DATA/'inference-quarantine.json').is_file() and not mac_mps_override_enabled()
    if quarantined:
        commands.pop('worker')
        print('Inference paused after a graphics crash. Starting evidence review, API and research only.',flush=True)
    if not quarantined and not mac_mps_override_enabled() and (ROOT/'infrastructure/launch/installed.json').is_file():
        commands['launch']=([str(python),'-u',str(ROOT/'scripts/launch_agent.py')],ROOT)
    children = {}
    handles = []
    instance = str(uuid.uuid4())
    job = OwnedJob()
    try:
        for name, (command, cwd) in commands.items():
            handle = (DATA / 'logs' / f'{name}-service.log').open('ab')
            handles.append(handle)
            children[name] = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            job.add(children[name])
        manifest = {'instance': instance, 'pid': os.getpid(), 'children': {name: child.pid for name, child in children.items()}, 'started_at': time.time(), 'binding': '127.0.0.1 only'}
        STATE.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print('Starting NeuroLoop. Logs: ' + str(DATA / 'logs'), flush=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            failed = {name: child.returncode for name, child in children.items() if child.poll() is not None}
            if failed:
                raise RuntimeError('A service exited during startup: ' + json.dumps(failed) + '. Inspect its service log.')
            if all(endpoint_ready(url) for url in ['http://127.0.0.1:8010/health', 'http://127.0.0.1:3010', 'http://127.0.0.1:2718']):
                break
            time.sleep(1)
        else:
            raise RuntimeError('Service readiness timed out. No success was assumed; inspect service logs.')
        print('Web:      http://localhost:3010', flush=True)
        print('MCP:      http://127.0.0.1:8010/mcp  (authenticated)', flush=True)
        print('Research: http://localhost:2718', flush=True)
        stop_name = 'Stop-NeuroLoop.cmd' if os.name == 'nt' else './Stop-NeuroLoop.sh'
        print(f'Local single-workspace deployment. Press Ctrl+C or run {stop_name} to stop.', flush=True)
        if open_browser:
            webbrowser.open('http://localhost:3010/workspace')
        while not STOP.exists():
            failed = {name: child.returncode for name, child in children.items() if child.poll() is not None}
            if failed:
                raise RuntimeError('Service stopped unexpectedly: ' + json.dumps(failed))
            time.sleep(1)
    except KeyboardInterrupt:
        print('Stopping owned services...', flush=True)
    finally:
        stop_children(children)
        job.close()
        for handle in handles:
            handle.close()
        try:
            current = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
            if current.get('instance') == instance:
                STATE.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            pass
        STOP.unlink(missing_ok=True)
        print('NeuroLoop services stopped. Completed results remain on disk.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['serve', 'status', 'stop'])
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--model-runtime', choices=['model','model-rehearsal'], default='model', help='Use the clean rehearsal environment only for release verification')
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(get_status(), indent=2))
    elif args.action == 'stop':
        if not STATE.exists():
            print('No supervisor record exists. No unrelated process was terminated.')
            return
        STOP.write_text('stop\n', encoding='utf-8')
        print('Stop requested. The supervisor will stop only its own child services.')
    else:
        serve(not args.no_browser,args.model_runtime)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
