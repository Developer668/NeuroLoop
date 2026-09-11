"""Anatomical summaries on the exact fsaverage5 vertex order, without psychological inference."""
from functools import lru_cache
import hashlib
import json
import numpy as np
from .config import settings
from .readout import validate_response

@lru_cache(maxsize=1)
def atlas():
    path = settings().data / 'geometry/atlas.json'
    raw = path.read_bytes()
    item = json.loads(raw)
    if item['mesh'] != 'fsaverage5' or len(item['left']) != 10242 or len(item['right']) != 10242:
        raise ValueError('Atlas vertex order or resolution does not match the response')
    return item, hashlib.sha256(raw).hexdigest()

def summarize_regions(response):
    x = validate_response(response)
    source, digest = atlas()
    regions = []
    for hemisphere, offset in [('left', 0), ('right', 10242)]:
        mapping = np.asarray(source[hemisphere])
        for index, label in enumerate(source['labels']):
            mask = mapping == index
            if not mask.any() or label.lower() in {'unknown', 'medial_wall'}:
                continue
            values = x[:, offset:offset + 10242][:, mask]
            regions.append({'id': f'{hemisphere}:{index}', 'hemisphere': hemisphere,
                'name': label.replace('_', ' '), 'vertices': int(mask.sum()),
                'mean': values.mean(axis=1).tolist(), 'rms': float(np.sqrt(np.mean(values ** 2)))})
    return {'atlas': source['atlas'], 'mesh': source['mesh'], 'sha256': digest,
            'regions': regions, 'units': 'model-response units',
            'interpretation': 'Anatomical parcel averages; no emotion or cognitive function is inferred.'}
