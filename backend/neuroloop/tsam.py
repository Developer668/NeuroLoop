"""Strict, CPU-only adapter for the original TSAM inference implementation.

The public checkpoint is a composite eight-class network, not a plain backbone.
No missing layer is tolerated. Scores are uncalibrated class logits and remain
separate from TRIBE. Response-target runs may combine them only through the explicit, versioned ensemble.
"""
from __future__ import annotations
import contextlib
import gc
import hashlib
import io
import json
import shutil
import sys
import time
from pathlib import Path

from .config import settings
from .media import execute

LABELS = ['Anger', 'Contempt', 'Disgust', 'Fear', 'Happiness', 'Neutral', 'Sadness', 'Surprise']
SOURCE_REVISION = '890540450e9459b9f917b2c50204b5be6fe72433'


def load_model():
    import numpy as np
    import torch
    import timm
    root = settings().root / 'models/emotion/tsam'
    source = root / 'source-code'
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from lib.model.backbone import BackBone
    from lib.model.prepare_input import X_input
    from lib.model.model import VCM

    class StrictBackbone(BackBone):
        def prepare_base_model(self, param):
            model = timm.create_model('resnet50', pretrained=False)
            model.last_layer_name = 'fc'
            return model

    args = json.loads((source / 'config/default.json').read_text())
    args['TSM']['num_class'] = 8
    args.update(video_segments=12, audio_segments=1, segment_frames=1)
    with contextlib.redirect_stdout(io.StringIO()):
        model = VCM(args['TSM'], X_input(args['TSM']), StrictBackbone(args['TSM']))
    checkpoint = root / 'weights/tsam_weights.tar'
    allowed = [(np._core.multiarray.scalar, 'numpy.core.multiarray.scalar'), np.dtype, np.dtypes.Float64DType]
    with torch.serialization.safe_globals(allowed):
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)['model_state']
    if set(state) != set(model.model_layers):
        raise ValueError('TSAM checkpoint sections do not match the approved architecture')
    for name, layer in model.model_layers.items():
        layer.load_state_dict(state[name], strict=True)
    model.eval().requires_grad_(False)
    return model, args


def predict_video(path: Path, duration: float, output: Path) -> dict:
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio
    from torchvision.transforms import Resize
    if duration < 5:
        return {'status': 'not_applicable', 'reason': 'TSAM requires a complete five-second audiovisual clip.'}
    started = time.monotonic()
    torch.set_num_threads(4)
    from lib.dataset.video import get_video_x
    work = output / 'tsam'; frames = work / 'frames'
    frames.mkdir(parents=True, exist_ok=True)
    model = args = None
    try:
        model, args = load_model()
        # Preserve upstream 10 FPS JPEG extraction and original audio sample rate.
        execute(['-y', '-i', str(path), '-vf', 'scale=-1:256,fps=10', '-q:v', '0', str(frames / '%06d.jpg')])
        wave = work / 'audio.wav'
        execute(['-y', '-i', str(path), '-vn', '-c:a', 'pcm_s16le', str(wave)])
        waveform, sr = sf.read(wave, dtype='float32', always_2d=True)
        if sr * .1 > 4800:
            raise ValueError('Audio sample rate exceeds the TSAM FFT window; resampling would require a new profile.')
        frame_count = len(list(frames.glob('*.jpg')))
        windows = []
        # Evaluate every full five-second window; preserve the explicitly omitted tail.
        with torch.inference_mode():
            for start in range(0, int(duration) - 4, 5):
                record = {'t': start, 'imagefolder': str(frames), 'imagefolder_size': frame_count}
                video = get_video_x(record, args, 'validation').unsqueeze(0)
                clip = torch.from_numpy(waveform[start * sr:(start + 5) * sr, 0].copy())
                if len(clip) < 5 * sr:
                    raise ValueError('Audio does not cover the complete TSAM window')
                channels = []
                for win, hop in zip([25, 50, 100], [10, 25, 50]):
                    mel = torchaudio.transforms.MelSpectrogram(sample_rate=sr, n_fft=4800,
                        win_length=round(win * sr / 1000), hop_length=round(hop * sr / 1000), n_mels=224)(clip)
                    channels.append(Resize((224, 224))(torch.log(mel + 1e-6).unsqueeze(0))[0])
                audio = torch.stack(channels).reshape(1, 1, 1, 3, 224, 224)
                logits = model(video, audio)[0].numpy()
                if logits.shape != (8,) or not np.isfinite(logits).all():
                    raise ValueError('Invalid TSAM output; no substitute result is emitted')
                windows.append({'start': start, 'end': start + 5, 'logits': logits.tolist(),
                                'top_class': LABELS[int(logits.argmax())]})
        checkpoint = settings().root / 'models/emotion/tsam/weights/tsam_weights.tar'
        return {'status': 'experimental', 'evaluator': 'TSAM', 'labels': LABELS, 'windows': windows,
                'seconds': time.monotonic() - started, 'device': 'cpu',
                'weights_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                'source_revision': SOURCE_REVISION, 'profile': 'upstream-default-12RGB-1audio-5s-cpu-v1',
                'class_order_source': 'Original setup_data.py and mvlib/mvideo_lib.py; includes Neutral.',
                'input': 'Independent audiovisual stimulus; no TRIBE response is fed into TSAM.',
                'omitted_tail_seconds': duration - windows[-1]['end'],
                'interpretation': 'Uncalibrated eight-class logits. Not probabilities or observed viewer emotions.',
                'limitations': ['Upstream default inference configuration; original training configuration is not embedded in the checkpoint.',
                                'Strict loading verifies architecture compatibility, not predictive validity on your creative.',
                                'Research-use licensing applies. When explicitly selected for response-target optimization, the versioned ensemble may use this relative evidence for keep/revert decisions.']}
    finally:
        del model, args
        gc.collect()
        shutil.rmtree(work, ignore_errors=True)
