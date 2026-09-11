"""Explicitly install the one missing speech-preprocessing checkpoint.
Not a content evaluator; no training, no automatic downloads during inference.
"""
from pathlib import Path
import json
from faster_whisper.utils import download_model
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'models/preprocessing/faster-whisper-small'
print('Installing local speech transcription from Systran/faster-whisper-small',flush=True)
location=download_model('small',output_dir=str(target))
files={p.name:p.stat().st_size for p in target.iterdir() if p.is_file()}
assert (target/'model.bin').is_file()
manifest={'source':'https://huggingface.co/Systran/faster-whisper-small','purpose':'Local English word timestamps for TRIBE language events','training':False,'files':files}
(target/'neuroloop-provenance.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2),flush=True)
