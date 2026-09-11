"""Validate local shard maps before Transformers/Accelerate may load weights."""
import json,stat
from pathlib import Path,PureWindowsPath,PurePosixPath

def validate_shards(folder: Path):
    root=folder.resolve();checked=[]
    for index in root.glob('*.index.json'):
        data=json.loads(index.read_text(encoding='utf8'))
        mapping=data.get('weight_map')
        if not isinstance(mapping,dict) or not mapping:raise ValueError('Checkpoint index has no weight map')
        for shard in set(mapping.values()):
            if not isinstance(shard,str) or not shard or ':' in shard:
                raise ValueError('Invalid checkpoint shard name')
            win=PureWindowsPath(shard);posix=PurePosixPath(shard)
            if win.is_absolute() or posix.is_absolute() or '..' in win.parts or '..' in posix.parts:
                raise ValueError('Checkpoint shard must stay within its model directory')
            target=(root/shard).resolve()
            if not target.is_relative_to(root) or not target.exists() or not stat.S_ISREG(target.stat().st_mode):
                raise ValueError('Checkpoint shard is missing, outside its directory, or not a regular file')
        checked.append(index.name)
    return checked
