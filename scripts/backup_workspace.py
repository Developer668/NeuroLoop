"""Consistent local backup/restore. Stop services first; restore only to a new directory."""
from __future__ import annotations
import argparse,hashlib,json,shutil,socket,sqlite3
from pathlib import Path, PurePosixPath, PureWindowsPath
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=('assets','renders','results','geometry')

def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def check_database(root):
    errors=[]
    with sqlite3.connect(f'file:{(root/"data/neuroloop.db").as_posix()}?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': errors.append('SQLite integrity failure')
        for identity,path,expected in db.execute('SELECT id,path,sha256 FROM assets'):
            p=Path(path)
            if not p.is_file() or digest(p)!=expected: errors.append('Asset mismatch: '+identity)
        for identity,path in db.execute('SELECT id,prediction_path FROM evaluations WHERE prediction_path IS NOT NULL'):
            if not Path(path).is_file(): errors.append('Missing prediction: '+identity)
        orphan=db.execute('SELECT count(*) FROM runs r LEFT JOIN projects p ON p.id=r.project_id WHERE p.id IS NULL').fetchone()[0]
        if orphan: errors.append(f'{orphan} orphan runs')
    if errors: raise ValueError('; '.join(errors))
    return {'integrity':'ok','assets':'all SHA-256 matched','predictions':'all present','orphan_runs':0}

def ensure_stopped():
    for port in (3010,8010,2718):
        with socket.socket() as connection:
            connection.settimeout(.2)
            if connection.connect_ex(('127.0.0.1',port))==0: raise ValueError('Stop NeuroLoop services before a consistent backup')
    with sqlite3.connect(ROOT/'data/neuroloop.db') as db:
        if db.execute("SELECT count(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0]:
            raise ValueError('Resolve queued/running jobs before backup')

def backup(target):
    ensure_stopped();check_database(ROOT)
    target=target.resolve()
    if target.exists(): raise ValueError('Backup target must be a new directory')
    if any(target.is_relative_to(ROOT/'data'/d) for d in DIRECTORIES): raise ValueError('Backup cannot be nested in a copied data directory')
    target.mkdir(parents=True)
    (target/'data').mkdir()
    with sqlite3.connect(ROOT/'data/neuroloop.db') as source,sqlite3.connect(target/'data/neuroloop.db') as destination:
        source.backup(destination)
    for name in DIRECTORIES:
        if (ROOT/'data'/name).exists(): shutil.copytree(ROOT/'data'/name,target/'data'/name)
    for name in ('preferences.json','inference-quarantine.json'):
        if (ROOT/'data'/name).is_file():shutil.copy2(ROOT/'data'/name,target/'data'/name)
    files={p.relative_to(target).as_posix():digest(p) for p in (target/'data').rglob('*') if p.is_file()}
    manifest={'version':1,'created_at':datetime.now(timezone.utc).isoformat(),'source_root':str(ROOT),'files':files,'excluded':'Model weights, caches, credentials, runtime packages, source code and historical audit bundles are separate recovery inputs.'}
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return {'backup':str(target),'files':len(files)}

def restore(source,target):
    source=source.resolve();target=target.resolve()
    if target.exists():raise ValueError('Restore target must be a new directory; existing workspaces are never overwritten')
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf8'))
    if manifest['version']!=1:raise ValueError('Unsupported backup version')
    for name,expected in manifest['files'].items():
        if len(PurePosixPath(name).parts)<2 or '\\' in name or ':' in name or PureWindowsPath(name).drive or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or PurePosixPath(name).parts[0]!='data':
            raise ValueError('Backup paths must be relative data paths without traversal')
        p=(source/name).resolve()
        if not p.is_relative_to(source/'data') or not p.is_file() or digest(p)!=expected:raise ValueError('Backup checksum/path validation failed')
    target.mkdir(parents=True)
    for name in manifest['files']:
        destination=target/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/name,destination)
    old=manifest['source_root'];new=str(target)
    def relocate(value):
        if isinstance(value,str): return value.replace(old,new).replace(old.replace('\\','/'),new.replace('\\','/'))
        if isinstance(value,list): return [relocate(v) for v in value]
        if isinstance(value,dict): return {k:relocate(v) for k,v in value.items()}
        return value
    with sqlite3.connect(target/'data/neuroloop.db') as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            # Identifiers come only from SQLite schema, never command-line text.
            quoted='"'+table.replace('"','""')+'"'
            columns=[r[1] for r in db.execute('PRAGMA table_info('+quoted+')') if r[2].upper() in ('TEXT','JSON')]
            for column in columns:
                col='"'+column.replace('"','""')+'"'
                for rowid,value in db.execute(f'SELECT rowid,{col} FROM {quoted} WHERE {col} IS NOT NULL').fetchall():
                    try: updated=json.dumps(relocate(json.loads(value)))
                    except (ValueError,TypeError):updated=relocate(value)
                    if updated!=value:db.execute(f'UPDATE {quoted} SET {col}=? WHERE rowid=?',(updated,rowid))
        # Restored remote deliveries are historical receipts; do not replay exports.
        db.execute("UPDATE external_receipts SET status='held_after_restore' WHERE status IN ('pending','retry')")
    hold=target/'data/inference-quarantine.json'
    if not hold.exists():
        hold.write_text(json.dumps({'version':1,'active':True,'reason':'Restored workspace requires explicit execution review before starting model or Launch work.','cause_confirmed':False}),encoding='utf8')
    checked=check_database(target)
    (target/'restore-report.json').write_text(json.dumps(checked,indent=2),encoding='utf8')
    return {'restored':str(target),**checked}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['backup','restore','check'])
    parser.add_argument('path',type=Path)
    parser.add_argument('--target',type=Path)
    args=parser.parse_args()
    if args.action=='restore' and args.target is None:parser.error('restore requires --target')
    result=backup(args.path) if args.action=='backup' else restore(args.path,args.target) if args.action=='restore' else check_database(args.path)
    print(json.dumps(result,indent=2))
