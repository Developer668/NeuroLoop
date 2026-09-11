"""Real checkpoint inference on a deterministic technical video fixture. No fabricated neural data."""
from pathlib import Path
import os, sys, json, time, subprocess
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
import imageio_ffmpeg
import pandas as pd
import numpy as np
import torch
from neuralset.events.utils import standardize_events
from models.load_local_tribe import load_local_tribe

def main():
    torch.set_num_threads(6)
    folder=ROOT/'data/verification'; folder.mkdir(exist_ok=True)
    video=folder/'technical-motion-fixture.mp4'
    if not video.exists():
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x240:rate=12','-t','6','-an','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,timeout=60)
    start=time.monotonic()
    model=load_local_tribe('cuda')
    model.data.batch_size=1
    model.data.num_workers=0
    events=standardize_events(pd.DataFrame([{'type':'Video','filepath':str(video),'start':0.0,'duration':6.0,'timeline':'fixture','subject':'default'}]))
    print('EVENTS',events.to_string(),flush=True)
    predictions,segments=model.predict(events,verbose=False)
    assert predictions.ndim==2 and predictions.shape[1]==20484 and predictions.shape[0]>0
    assert np.isfinite(predictions).all()
    np.save(folder/'real-tribe-predictions.npy',predictions)
    result={'passed':True,'fixture':'deterministic motion test pattern, no audio or speech','shape':list(predictions.shape),'seconds':time.monotonic()-start,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'finite':True,'range':[float(predictions.min()),float(predictions.max())],'segment_examples':[{'start':float(s.start),'duration':float(s.duration)} for s in segments[:10]],'scope':'Real video decoder, actual quantized V-JEPA encoder and original TRIBE brain weights. Not a human-preference validation.'}
    (folder/'tribe-e2e.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__': main()
