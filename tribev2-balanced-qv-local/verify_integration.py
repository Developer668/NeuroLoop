"""Test the TRIBE adapter and brain forward without downloading text/audio models."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def main():
    sys.path.insert(0, str(PROJECT_ROOT / 'backend'))
    from neuroloop.hardware import require_inference_headroom
    preflight = require_inference_headroom()
    import numpy as np
    import torch
    from load_quantized_tribev2 import ROOT, load_quantized_tribev2
    from neuralset.extractors.video import _HFVideoModel

    device = preflight['accelerator']
    torch.set_num_threads(6)
    tribe = load_quantized_tribev2(device=device)
    assert tribe.data.video_feature.frequency == tribe.data.frequency == 2.0
    assert tribe.data.video_feature.image.batch_size == 1
    video = _HFVideoModel('facebook/vjepa2-vitg-fpc64-256')
    frames = np.random.default_rng(42).integers(0, 256, (64, 256, 256, 3), dtype=np.uint8)
    features = video.predict_hidden_states(frames)
    assert features.shape == (1, 41, 8192, 1408)
    assert torch.isfinite(features).all()
    del features, video
    if device == 'cuda':
        torch.cuda.empty_cache()
    elif device == 'mps':
        empty_cache = getattr(torch.mps, 'empty_cache', None)
        if callable(empty_cache):
            empty_cache()
    batch = SimpleNamespace(data={'video': torch.rand(1, 2, 1408, 100, device=device)})
    with torch.inference_mode():
        output = tribe._model(batch)
    assert output.shape == (1, 20484, 100) and torch.isfinite(output).all()
    report = {'passed': True, 'video_adapter_shape': [1, 41, 8192, 1408],
              'brain_output_shape': list(output.shape), 'device': device,
              'hardware_preflight': preflight,
              'video_frequency_hz': tribe.data.video_feature.frequency,
              'video_batch_size_setting': tribe.data.video_feature.image.batch_size,
              'scope': 'Real processor and video adapter; synthetic features for brain forward. No end-to-end audio/text/fMRI evaluation.'}
    (ROOT / 'integration-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
