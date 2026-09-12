"""Inspect checkpoint metadata with a restricted deserializer; do not run a predictor."""
from pathlib import Path
import torch,numpy as np,json
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'models/emotion/tsam/weights/tsam_weights.tar'
found=set(torch.serialization.get_unsafe_globals_in_checkpoint(path))
allowed={'numpy.dtype','numpy.core.multiarray.scalar'}
if found-allowed:raise RuntimeError('Unapproved serialized globals: '+str(found-allowed))
def summarize(value,depth=0):
    if isinstance(value,torch.Tensor):return {'tensor_shape':list(value.shape),'dtype':str(value.dtype)}
    if isinstance(value,np.ndarray):return {'array_shape':list(value.shape),'dtype':str(value.dtype)}
    if depth>5:return str(type(value).__name__)
    if isinstance(value,dict):return {str(k):summarize(v,depth+1) for k,v in list(value.items())[:100]}
    if isinstance(value,(list,tuple)):return [summarize(x,depth+1) for x in value[:40]]
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    return str(type(value).__name__)
with torch.serialization.safe_globals([(np._core.multiarray.scalar,'numpy.core.multiarray.scalar'),np.dtype,np.dtypes.Float64DType]):
 checkpoint=torch.load(path,map_location='cpu',weights_only=True)
result={k:summarize(v) for k,v in checkpoint.items() if k!='optimizer_state_dict' and k!='model_state'}
result['model_sections']={k:{'entries':len(v),'first_keys':list(v)[:12]} for k,v in checkpoint['model_state'].items()}
(ROOT/'data/verification/tsam-metadata.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
