"""Fetch documented fsaverage5 surfaces; never fabricate cortical geometry."""
from pathlib import Path
import json,hashlib
import requests,nibabel as nib,numpy as np
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/geometry'; OUT.mkdir(parents=True,exist_ok=True)
BASE='https://raw.githubusercontent.com/nilearn/nilearn/0.12.1/nilearn/datasets/data/fsaverage5/'
manifest={'source':BASE,'mesh':'fsaverage5','hemisphere_order':['left','right'],'files':{}}
result={'mesh':'fsaverage5','units':'mm','hemispheres':[]}
for hemi in ['left','right']:
    display=None
    for surface in ['pial','white']:
        path=OUT/f'{surface}_{hemi}.gii.gz'
        if not path.exists():
            response=requests.get(BASE+path.name,timeout=60); response.raise_for_status(); path.write_bytes(response.content)
        gifti=nib.load(path)
        coords=next(a.data for a in gifti.darrays if a.intent==1008)
        faces=next(a.data for a in gifti.darrays if a.intent==1009)
        assert coords.shape==(10242,3) and faces.shape==(20480,3)
        assert np.isfinite(coords).all() and faces.max()<len(coords)
        manifest['files'][path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'vertices':len(coords),'faces':len(faces)}
        if surface=='pial': display=(coords,faces)
    coords,faces=display
    result['hemispheres'].append({'name':hemi,'positions':coords.astype(float).round(4).ravel().tolist(),'indices':faces.astype(int).ravel().tolist()})
(OUT/'fsaverage5.json').write_text(json.dumps(result,separators=(',',':')))
(OUT/'provenance.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
