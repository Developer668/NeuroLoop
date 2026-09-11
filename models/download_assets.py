"""Download selected model data only, pin revisions, and verify upstream hashes."""
import hashlib
import json
from pathlib import Path
import requests
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent
SPECS = [
    ('facebook/w2v-bert-2.0', 'da985ba0987f70aaeb84a80f2851cfac8c697a7b', 'audio/w2v-bert-2.0'),
    ('facebook/dinov2-large', '47b73eefe95e8d44ec3623f8890bd894b6ea2d6c', 'vision/dinov2-large'),
    ('unsloth/Llama-3.2-3B-bnb-4bit', 'cd129a0e0b128fe4fb01e1bdca5e9af6a0c9a5d6', 'text/llama-3.2-3b-unsloth-q4'),
    ('dnamodel/tsam-viewer-emotions', '638a79e44591a0f213ea660f100040a1beb26ac2', 'emotion/tsam/weights'),
]

def digest(path, algorithm='sha256', git_blob=False):
    h = hashlib.new(algorithm)
    if git_blob:
        h.update(b'blob ' + str(path.stat().st_size).encode() + b'\0')
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    for repo, rev, folder in SPECS:
        response = requests.get(f'https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true', timeout=60)
        response.raise_for_status()
        info = response.json()
        files = [f for f in info['siblings'] if f['rfilename'].endswith(('.safetensors', '.json', '.md'))
                 or f['rfilename'] in ['LICENSE', 'LICENSE.txt', 'backbone_weights.tar', 'tsam_weights.tar']]
        dest = ROOT / folder
        print('Downloading', repo, flush=True)
        snapshot_download(repo, revision=rev, local_dir=dest, allow_patterns=[f['rfilename'] for f in files], token=False)
        records = []
        for f in files:
            path = dest / f['rfilename']
            sha = digest(path)
            if 'lfs' in f:
                assert sha == f['lfs']['sha256'], path
            else:
                assert digest(path, 'sha1', git_blob=True) == f['blobId'], path
            records.append({'file': f['rfilename'], 'bytes': path.stat().st_size, 'sha256': sha})
        (dest / 'download-manifest.json').write_text(json.dumps({'repo': repo, 'revision': rev, 'verified': True, 'files': records}, indent=2))
        print('Verified', repo, sum(f['bytes'] for f in records), 'bytes', flush=True)

if __name__ == '__main__':
    main()
