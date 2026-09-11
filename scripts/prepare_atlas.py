"""Install the documented Destrieux fsaverage5 atlas; never interpolate unknown vertex spaces."""
from pathlib import Path
import hashlib
import json
import numpy as np
from nilearn.datasets import fetch_atlas_surf_destrieux

ROOT=Path(__file__).resolve().parents[1]
atlas=fetch_atlas_surf_destrieux(data_dir=str(ROOT/'models/brain_readouts/anatomy'))
labels=[x.decode() if isinstance(x,bytes) else str(x) for x in atlas.labels]
left=np.asarray(atlas.map_left);right=np.asarray(atlas.map_right)
if left.shape!=(10242,) or right.shape!=(10242,):
    raise ValueError('The fetched atlas does not match fsaverage5')
result={'atlas':'Destrieux 2009','mesh':'fsaverage5',
        'source':'nilearn.datasets.fetch_atlas_surf_destrieux/0.12.1',
        'labels':labels,'left':left.tolist(),'right':right.tolist()}
out=ROOT/'data/geometry/atlas.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')
print(json.dumps({'path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
                  'vertices':len(left)+len(right)}))
