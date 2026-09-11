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
import math
import shutil
import sys
import time
from pathlib import Path

from .config import settings
from .media import execute
from .response import PROVENANCE_VERSION, TSAM_LABELS, TIME_AXIS_VERSION, normalized_axis

LABELS = list(TSAM_LABELS)
SOURCE_REVISION = '890540450e9459b9f917b2c50204b5be6fe72433'
MODEL_VERSION = 'tsam-viewer-emotions-upstream-v1'
PREPROCESSING_VERSION = 'tsam-default-12rgb-1audio-5s-v1'
WINDOW_SECONDS = 5
WINDOW_STRIDE_SECONDS = 5
VIDEO_FPS = 10
VIDEO_HEIGHT = 256
AUDIO_FFT = 4800
AUDIO_MEL_BANDS = 224
AUDIO_WINDOWS_MS = (25, 50, 100)
AUDIO_HOPS_MS = (10, 25, 50)


def preprocessing_contract() -> dict:
    """Exact preprocessing parameters used by the upstream adapter."""
    return {
        'version': PREPROCESSING_VERSION,
        'video': {'fps': VIDEO_FPS, 'scale_height': VIDEO_HEIGHT, 'segments': 12, 'segment_frames': 1,
                  'resize': 'upstream validation transform to 224x224'},
        'audio': {'segments': 1, 'sample_rate': 'source rate retained', 'n_fft': AUDIO_FFT,
                  'window_ms': list(AUDIO_WINDOWS_MS), 'hop_ms': list(AUDIO_HOPS_MS),
                  'mel_bands': AUDIO_MEL_BANDS, 'log_offset': 1e-6, 'resize': [224, 224],
                  'channels': 3},
        'window': {'seconds': WINDOW_SECONDS, 'stride_seconds': WINDOW_STRIDE_SECONDS,
                   'tail_policy': 'omit incomplete tail'},
        'class_order': LABELS,
    }


def _contract_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def window_plan(duration: float) -> list[dict[str, float | int]]:
    """Return complete non-overlapping five-second windows for a duration."""
    duration = float(duration)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError('TSAM duration must be finite and non-negative')
    count = int(duration // WINDOW_STRIDE_SECONDS)
    windows = []
    for index in range(count):
        start = index * WINDOW_STRIDE_SECONDS
        end = start + WINDOW_SECONDS
        if end <= duration + 1e-9:
            windows.append({'index': index, 'start': float(start), 'end': float(end), 'duration': float(WINDOW_SECONDS)})
    return windows


def _base_provenance(checkpoint_hash: str | None = None) -> dict:
    contract = preprocessing_contract()
    return {
        'contract_version': PROVENANCE_VERSION,
        'model': {'name': 'TSAM', 'version': MODEL_VERSION, 'source_revision': SOURCE_REVISION},
        'checkpoint': {'sha256': checkpoint_hash, 'version': 'tsam_weights.tar'},
        'preprocessing': {'version': PREPROCESSING_VERSION, 'sha256': _contract_hash(contract), 'contract': contract},
        'geometry': {'version': 'not_applicable/direct-media-v1', 'sha256': None, 'meaning': 'direct-media source; no cortical geometry'},
        'projection': {'version': 'not_applicable/direct-media-v1', 'sha256': None, 'meaning': 'direct-media source; no TRIBE projection'},
    }


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
    duration = float(duration)
    plan = window_plan(duration)
    if not plan:
        return {
            'status': 'not_applicable', 'source_kind': 'direct_media', 'reason': 'TSAM requires a complete five-second audiovisual clip.',
            'evaluator': 'TSAM', 'labels': LABELS, 'source_duration': duration,
            'time_axis': [], 'omitted_tail_seconds': duration, 'tail_policy': 'omit incomplete tail',
            'profile': PREPROCESSING_VERSION, 'provenance': _base_provenance(),
        }
    started = time.monotonic()
    torch.set_num_threads(4)
    from lib.dataset.video import get_video_x
    work = output / 'tsam'; frames = work / 'frames'
    frames.mkdir(parents=True, exist_ok=True)
    model = args = None
    try:
        model, args = load_model()
        # Preserve upstream 10 FPS JPEG extraction and 256-pixel height.
        execute(['-y', '-i', str(path), '-vf', f'scale=-1:{VIDEO_HEIGHT},fps={VIDEO_FPS}', '-q:v', '0', str(frames / '%06d.jpg')])
        wave = work / 'audio.wav'
        execute(['-y', '-i', str(path), '-vn', '-c:a', 'pcm_s16le', str(wave)])
        waveform, sr = sf.read(wave, dtype='float32', always_2d=True)
        if sr * .1 > AUDIO_FFT:
            raise ValueError('Audio sample rate exceeds the TSAM FFT window; resampling would require a new profile.')
        frame_count = len(list(frames.glob('*.jpg')))
        windows = []
        # Evaluate every full five-second window; preserve the explicitly omitted tail.
        with torch.inference_mode():
            for window in plan:
                start = int(window['start'])
                record = {'t': start, 'imagefolder': str(frames), 'imagefolder_size': frame_count}
                video = get_video_x(record, args, 'validation').unsqueeze(0)
                clip = torch.from_numpy(waveform[start * sr:(start + WINDOW_SECONDS) * sr, 0].copy())
                if len(clip) < WINDOW_SECONDS * sr:
                    raise ValueError('Audio does not cover the complete TSAM window')
                channels = []
                for win, hop in zip(AUDIO_WINDOWS_MS, AUDIO_HOPS_MS):
                    mel = torchaudio.transforms.MelSpectrogram(sample_rate=sr, n_fft=AUDIO_FFT,
                        win_length=round(win * sr / 1000), hop_length=round(hop * sr / 1000), n_mels=AUDIO_MEL_BANDS)(clip)
                    channels.append(Resize((224, 224))(torch.log(mel + 1e-6).unsqueeze(0))[0])
                audio = torch.stack(channels).reshape(1, 1, 1, 3, 224, 224)
                logits = model(video, audio)[0].numpy()
                if logits.shape != (8,) or not np.isfinite(logits).all():
                    raise ValueError('Invalid TSAM output; no substitute result is emitted')
                windows.append({**window, 'start': start, 'end': start + WINDOW_SECONDS,
                                'logits': logits.tolist(), 'top_class': LABELS[int(logits.argmax())]})
                del video, clip, channels, audio, logits
        checkpoint = settings().root / 'models/emotion/tsam/weights/tsam_weights.tar'
        checkpoint_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        axis = normalized_axis(windows, duration, source='tsam')
        for window, item in zip(windows, axis):
            window.update({'start_norm': item['start_norm'], 'end_norm': item['end_norm'], 'axis_version': TIME_AXIS_VERSION})
        return {'status': 'experimental', 'source_kind': 'direct_media', 'evaluator': 'TSAM', 'labels': LABELS, 'windows': windows,
                'source_duration': duration, 'time_axis': axis, 'tail_policy': 'omit incomplete tail',
                'seconds': time.monotonic() - started, 'device': 'cpu',
                'weights_sha256': checkpoint_hash,
                'source_revision': SOURCE_REVISION, 'profile': PREPROCESSING_VERSION,
                'class_order_source': 'Original setup_data.py and mvlib/mvideo_lib.py; includes Neutral.',
                'input': 'Independent audiovisual stimulus; no TRIBE response is fed into TSAM.',
                'omitted_tail_seconds': max(0.0, duration - windows[-1]['end']),
                'preprocessing': preprocessing_contract(),
                'provenance': _base_provenance(checkpoint_hash),
                'interpretation': 'Uncalibrated eight-class logits. Not probabilities or observed viewer emotions.',
                'limitations': ['Upstream default inference configuration; original training configuration is not embedded in the checkpoint.',
                                'Strict loading verifies architecture compatibility, not predictive validity on your creative.',
                                'Research-use licensing applies. When explicitly selected for response-target optimization, the versioned ensemble may use this relative evidence for keep/revert decisions.']}
    finally:
        del model, args
        gc.collect()
        shutil.rmtree(work, ignore_errors=True)
