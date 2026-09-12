"""Numerical readout, not a psychological decoder. No learned weights are changed."""
from __future__ import annotations
import numpy as np

METRIC='spatially-centered-cosine/eight-normalized-time-bins/v1'

def validate_response(response: np.ndarray) -> np.ndarray:
    x=np.asarray(response,dtype=np.float64)
    if x.ndim!=2 or x.shape[1]!=20484 or x.shape[0]<1:
        raise ValueError('Expected a nonempty time-by-20,484 cortical array')
    if not np.isfinite(x).all(): raise ValueError('Non-finite cortical data is not scoreable')
    return x

def fingerprint(response: np.ndarray, bins: int=8) -> np.ndarray:
    x=validate_response(response)
    # This is explicitly a reference-comparison representation, not brain anatomy.
    xp=np.linspace(0,1,len(x)); grid=np.linspace(0,1,bins)
    if len(x)==1: pooled=np.repeat(x,bins,axis=0)
    else:
        positions=grid*(len(x)-1)
        lo=np.floor(positions).astype(int); hi=np.minimum(lo+1,len(x)-1)
        weight=(positions-lo)[:,None]
        pooled=x[lo]*(1-weight)+x[hi]*weight
    pooled=pooled-pooled.mean(axis=1,keepdims=True)
    norms=np.linalg.norm(pooled,axis=1,keepdims=True)
    if np.any(norms<1e-12): raise ValueError('Degenerate cortical pattern cannot be compared')
    return pooled/norms

def similarity(candidate: np.ndarray, reference: np.ndarray) -> float:
    a=fingerprint(candidate); b=fingerprint(reference)
    return float(np.clip(np.mean(np.sum(a*b,axis=1)),-1,1))

def compare_references(candidate: np.ndarray,references: list[tuple[str,np.ndarray]]) -> dict:
    if not references: raise ValueError('A reference is required for a neural-reference objective')
    scores=[{'reference_id':identity,'value':similarity(candidate,array)} for identity,array in references]
    values=[s['value'] for s in scores]
    return {'metric':METRIC,'value':float(np.mean(values)),'per_reference':scores,'range':[min(values),max(values)],'scale':[-1,1],'evidence_type':'model-reference-similarity','interpretation':'Agreement of predicted cortical patterns under a fixed numerical representation; not human liking or purchase probability.'}

def summarize(response: np.ndarray,times: list[float]) -> dict:
    x=validate_response(response)
    if len(times)!=len(x): raise ValueError('Segment timestamps and prediction rows do not match')
    return {'shape':list(x.shape),'times':times,'left_mean':x[:,:10242].mean(axis=1).tolist(),'right_mean':x[:,10242:].mean(axis=1).tolist(),'rms':np.sqrt(np.mean(x*x,axis=1)).tolist(),'range':[float(x.min()),float(x.max())],'mesh':'fsaverage5','units':'model response units','hemisphere_order':['left','right']}
