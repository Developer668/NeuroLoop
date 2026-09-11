"""Test the TRIBE adapter and brain forward without downloading text/audio models."""
import json
from types import SimpleNamespace
import numpy as np
import torch
from load_quantized_tribev2 import ROOT, load_quantized_tribev2

torch.set_num_threads(6)
tribe = load_quantized_tribev2(device='cuda')
assert tribe.data.video_feature.frequency == tribe.data.frequency == 2.0
assert tribe.data.video_feature.image.batch_size == 4
from neuralset.extractors.video import _HFVideoModel
video = _HFVideoModel('facebook/vjepa2-vitg-fpc64-256')
frames = np.random.default_rng(42).integers(0, 256, (64, 256, 256, 3), dtype=np.uint8)
features = video.predict_hidden_states(frames)
assert features.shape == (1, 41, 8192, 1408)
assert torch.isfinite(features).all()
del features, video
torch.cuda.empty_cache()
batch = SimpleNamespace(data={'video': torch.rand(1, 2, 1408, 100, device='cuda')})
with torch.inference_mode():
    output = tribe._model(batch)
assert output.shape == (1, 20484, 100) and torch.isfinite(output).all()
report = {'passed': True, 'video_adapter_shape': [1, 41, 8192, 1408],
          'brain_output_shape': list(output.shape),
          'video_frequency_hz': tribe.data.video_feature.frequency,
          'video_batch_size_setting': tribe.data.video_feature.image.batch_size,
          'scope': 'Real processor and video adapter; synthetic features for brain forward. No end-to-end audio/text/fMRI evaluation.'}
(ROOT / 'integration-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
