"""Atomic result publication: the final path is never a half-written artifact."""
from __future__ import annotations
import json,os,tempfile
from pathlib import Path
from typing import Any

def _publish(path:Path,writer) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.partial',dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            writer(stream)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)

def atomic_json(path:Path,value:Any) -> None:
    encoded=json.dumps(value,indent=2,allow_nan=False).encode('utf8')
    _publish(path,lambda stream:stream.write(encoded))

def atomic_numpy(path:Path,value) -> None:
    import numpy as np
    _publish(path,lambda stream:np.save(stream,value,allow_pickle=False))
