"""Exercise the pinned MoviePy/Pillow fork on managed NASA video, without GPU work."""
from pathlib import Path
import importlib.metadata as metadata,json,sys
import numpy as np
from moviepy import VideoFileClip
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'data/assets/4308bd50-42c1-4eb1-94e3-103964df7ac6.mp4'
out=ROOT/'data/verification/release';out.mkdir(parents=True,exist_ok=True)
destination=out/'moviepy-resize.mp4'
with VideoFileClip(str(source),audio=False) as original:
    short=original.subclipped(0,1).resized(width=160)
    short.write_videofile(str(destination),fps=10,codec='libx264',audio=False,logger=None,threads=2)
with VideoFileClip(str(destination),audio=False) as output:
    frame=output.get_frame(.5)
    assert frame.shape==(90,160,3) and np.isfinite(frame).all() and frame.std()>0
    report={'python':sys.executable,'moviepy':metadata.version('moviepy'),'pillow':metadata.version('pillow'),'numpy':metadata.version('numpy'),'source':str(source),'output':str(destination),'frame_shape':list(frame.shape),'duration':output.duration,'passed':True}
(out/'moviepy-rehearsal.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
