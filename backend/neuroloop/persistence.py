"""Atomic result publication: the final path is never a half-written artifact."""
from __future__ import annotations
import hashlib,json,os,tempfile
from pathlib import Path
from typing import Any

ARTIFACT_MANIFEST_NAME = 'artifact-manifest.json'
ARTIFACT_MANIFEST_VERSION = 'evaluation-artifacts/v1'
ARTIFACT_FILES = ('prediction.npy', 'segments.json', 'evidence.json')

class ArtifactIntegrityError(RuntimeError):
    """A published evaluation bundle is missing, changed, or inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def _publish_immutable_json(path: Path, encoded: bytes) -> None:
    """Publish a JSON record once, without replacing an existing record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if path.is_symlink():
            raise ArtifactIntegrityError(f'Cannot overwrite immutable artifact manifest: {path.name}')
        if path.read_bytes() == encoded:
            return
        raise ArtifactIntegrityError(f'Cannot overwrite immutable artifact manifest: {path.name}')
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.partial', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise ArtifactIntegrityError(f'Cannot overwrite immutable artifact manifest: {path.name}')
    finally:
        temporary.unlink(missing_ok=True)


def publish_artifact_manifest(output: Path, *, cache_key: str, profile: str, asset_sha256: str, profile_manifest: dict | None = None) -> dict:
    """Hash and publish the final evaluation files exactly once."""
    output = output.resolve()
    files = {}
    for name in ARTIFACT_FILES:
        path = output / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != output:
            raise ArtifactIntegrityError(f'Cannot finalize incomplete evaluation artifact: {name}')
        files[name] = {'bytes': path.stat().st_size, 'sha256': sha256(path)}
    manifest = {
        'version': ARTIFACT_MANIFEST_VERSION,
        'cache_key': cache_key,
        'profile': profile,
        'asset_sha256': asset_sha256,
        'files': files,
    }
    if profile_manifest is not None:
        manifest['profile_manifest'] = profile_manifest
    manifest['manifest_sha256'] = hashlib.sha256(_canonical(manifest)).hexdigest()
    _publish_immutable_json(output / ARTIFACT_MANIFEST_NAME, _canonical(manifest))
    return manifest


def validate_artifact_manifest(output: Path, *, cache_key: str, profile: str, asset_sha256: str, profile_manifest: dict | None = None) -> dict:
    """Verify the immutable manifest and every final file it names."""
    output = output.resolve()
    path = output / ARTIFACT_MANIFEST_NAME
    if path.is_symlink() or not path.is_file() or path.resolve().parent != output:
        raise ArtifactIntegrityError('Evaluation artifact manifest is missing or invalid')
    try:
        manifest = json.loads(path.read_text(encoding='utf8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ArtifactIntegrityError('Evaluation artifact manifest is missing or invalid') from exc
    if not isinstance(manifest, dict) or manifest.get('version') != ARTIFACT_MANIFEST_VERSION:
        raise ArtifactIntegrityError('Unsupported evaluation artifact manifest')
    recorded_digest = manifest.get('manifest_sha256')
    unsigned = dict(manifest)
    unsigned.pop('manifest_sha256', None)
    actual_digest = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if recorded_digest != actual_digest:
        raise ArtifactIntegrityError('Evaluation artifact manifest hash mismatch')
    for name, expected in (('cache_key', cache_key), ('profile', profile), ('asset_sha256', asset_sha256)):
        if manifest.get(name) != expected:
            raise ArtifactIntegrityError(f'Evaluation artifact {name} does not match the requested identity')
    if profile_manifest is not None and manifest.get('profile_manifest') != profile_manifest:
        raise ArtifactIntegrityError('Evaluation artifact profile snapshot does not match the requested identity')
    files = manifest.get('files')
    if not isinstance(files, dict) or set(files) != set(ARTIFACT_FILES):
        raise ArtifactIntegrityError('Evaluation artifact manifest has an incomplete file set')
    for name in ARTIFACT_FILES:
        item = files.get(name)
        target = output / name
        if not isinstance(item, dict) or target.is_symlink() or not target.is_file() or target.resolve().parent != output:
            raise ArtifactIntegrityError(f'Published evaluation artifact is missing: {name}')
        if item.get('bytes') != target.stat().st_size or item.get('sha256') != sha256(target):
            raise ArtifactIntegrityError(f'Published evaluation artifact changed: {name}')
    return manifest


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

def close_mmap(value) -> None:
    """Close an np.load mmap without assuming every ndarray is memory-mapped."""
    mapping = getattr(value, '_mmap', None)
    if mapping is not None:
        mapping.close()
