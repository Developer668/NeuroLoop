"""Verify clean stop/restart of idle owned services; leave the app running."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'data/services.json'
URLS = ['http://127.0.0.1:8010/health', 'http://127.0.0.1:3010', 'http://127.0.0.1:2718']

def ready(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (OSError, TimeoutError):
        return False

def main():
    import sqlite3
    with sqlite3.connect(f'file:{ROOT / "data/neuroloop.db"}?mode=ro', uri=True) as db:
        assert db.execute("select count(*) from runs where status in ('running','queued')").fetchone()[0] == 0, 'Do not interrupt user jobs'
    previous = json.loads(STATE.read_text())
    supervisor = psutil.Process(previous['pid'])
    owned = supervisor.children(recursive=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/manage.py'), 'stop'], check=True)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if not STATE.exists() and not any(ready(url) for url in URLS):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('Owned services did not stop')
    for process in owned:
        try:
            process.wait(timeout=5)
        except psutil.NoSuchProcess:
            pass
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == 'nt' else 0
    with (ROOT / 'data/logs/supervisor.log').open('ab') as output:
        subprocess.Popen([sys.executable, str(ROOT / 'scripts/manage.py'), 'serve', '--no-browser'],
                         cwd=ROOT, stdout=output, stderr=output, stdin=subprocess.DEVNULL,
                         creationflags=flags, start_new_session=os.name != 'nt')
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if STATE.exists() and all(ready(url) for url in URLS):
            break
        time.sleep(1)
    else:
        raise RuntimeError('Services did not become ready after restart')
    current = json.loads(STATE.read_text())
    assert current['instance'] != previous['instance']
    report = {'passed': True, 'owned_descendants_stopped': len(owned),
              'readiness_urls': URLS, 'new_instance': current['instance'],
              'scope': 'Idle supervisor stop/start; no queued user runs interrupted. Worker timeout/cancel process termination is covered in backend tests.'}
    (ROOT / 'data/verification/lifecycle.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
