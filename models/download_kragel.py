"""Fetch only the Kragel 2015 maps, mesh, source description and license."""
import json
from pathlib import Path
import requests
from download_assets import digest

ROOT = Path(__file__).resolve().parent / 'brain_readouts/kragel2015/source'
REPO = 'canlab/Neuroimaging_Pattern_Masks'
REV = '107a4f18d80c0c2ea5ac0ae3ccf3398a80cad504'
PREFIX = 'Multivariate_signature_patterns/2015_Kragel_emotionClassificationBPLS/'

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    response = requests.get(f'https://api.github.com/repos/{REPO}/git/trees/{REV}?recursive=1', timeout=60)
    response.raise_for_status()
    selected = [x for x in response.json()['tree'] if x['type'] == 'blob' and
                ((x['path'].startswith(PREFIX) and x['path'].endswith(('.gii', '.hdr', '.img', '.md')))
                 or x['path'] in ['LICENSE', 'LICENSE.txt'])]
    manifest = []
    for entry in selected:
        r = requests.get(f'https://raw.githubusercontent.com/{REPO}/{REV}/{entry["path"]}', timeout=60)
        r.raise_for_status()
        target = ROOT / Path(entry['path']).name
        target.write_bytes(r.content)
        assert digest(target, 'sha1', git_blob=True) == entry['sha'], target
        manifest.append({'file': target.name, 'upstream_path': entry['path'], 'sha256': digest(target), 'bytes': target.stat().st_size})
    (ROOT / 'download-manifest.json').write_text(json.dumps({'repo': REPO, 'revision': REV, 'verified': True, 'files': manifest}, indent=2))
    print('Downloaded and verified', len(manifest), 'Kragel source files', flush=True)

if __name__ == '__main__':
    main()
