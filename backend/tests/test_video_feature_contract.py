"""Run with the model runtime: python -m unittest discover -s backend/tests -p test_video_feature_contract.py."""
import sys
import unittest
from pathlib import Path

try:
    import torch
except ImportError:
    torch = None


@unittest.skipIf(torch is None, 'Requires the isolated model runtime')
class VideoFeatureContract(unittest.TestCase):
    def test_token_compaction_preserves_official_two_group_features(self):
        import numpy as np
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tribev2-balanced-qv-local'))
        from load_quantized_tribev2 import _compact_hidden_states
        from neuralset.extractors.image import HuggingFaceImage
        torch.manual_seed(719)
        states = tuple(torch.randn(1, 13, 1408).to(torch.bfloat16) for _ in range(41))
        extractor = HuggingFaceImage(layers=[0.5, 0.75, 1.0], cache_n_layers=20,
                                    layer_aggregation='group_mean', token_aggregation='mean')
        original = torch.stack([x.float()[0] for x in states])
        compact = torch.stack([x[0] for x in _compact_hidden_states(states)])
        expected = extractor._aggregate_layers(extractor._aggregate_tokens(original).numpy())
        actual = extractor._aggregate_layers(extractor._aggregate_tokens(compact).numpy())
        self.assertEqual(actual.shape, (2, 1408))
        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-7)

    def test_static_reuse_requires_every_decoded_frame_to_match(self):
        import numpy as np
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tribev2-balanced-qv-local'))
        from load_quantized_tribev2 import _static_video_key
        frames = np.zeros((64, 8, 8, 3), dtype=np.uint8)
        self.assertEqual(_static_video_key(frames), _static_video_key(frames.copy()))
        changed = frames.copy()
        changed[1, 0, 0, 0] = 1
        self.assertIsNone(_static_video_key(changed))
        changed[:, 0, 0, 0] = 1
        self.assertNotEqual(_static_video_key(frames), _static_video_key(changed))
        self.assertNotEqual(_static_video_key(frames), _static_video_key(frames[:32]))
