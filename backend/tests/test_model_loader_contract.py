"""Model-free contracts for the local MPS/INT8 loader.

These tests intentionally inspect source text and AST only. They must not import
PyTorch model classes, load weights, initialize the TRIBE package, or run inference.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
LOCAL_TRIBE = ROOT / "models" / "load_local_tribe.py"
VIDEO_LOADER = ROOT / "tribev2-balanced-qv-local" / "load_quantized_tribev2.py"
README = ROOT / "tribev2-balanced-qv-local" / "README.md"


class ModelLoaderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local_source = LOCAL_TRIBE.read_text(encoding="utf-8")
        cls.video_source = VIDEO_LOADER.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")
        cls.video_tree = ast.parse(cls.video_source, filename=str(VIDEO_LOADER))

    def test_meta_construction_and_strict_checkpoint_assignment_are_retained(self):
        self.assertIn("with torch.device('meta'):", self.video_source)
        load_calls = [
            node
            for node in ast.walk(self.video_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "load_state_dict"
        ]
        self.assertEqual(len(load_calls), 1)
        keywords = {keyword.arg: keyword.value for keyword in load_calls[0].keywords}
        self.assertIsInstance(keywords["strict"], ast.Constant)
        self.assertTrue(keywords["strict"].value)
        self.assertIsInstance(keywords["assign"], ast.Constant)
        self.assertTrue(keywords["assign"].value)

    def test_mps_path_is_capability_gated_and_cpu_fallback_remains(self):
        self.assertIn("device == 'mps'", self.video_source)
        self.assertIn("backend='pread'", self.video_source)
        self.assertIn("device='cpu'", self.video_source)
        self.assertIn("if not loaded_on_device:", self.video_source)
        self.assertIn("model = model.to(device)", self.video_source)

    def test_dtype_and_hidden_state_device_contracts_are_unchanged(self):
        self.assertIn("dtype=torch.bfloat16", self.video_source)
        self.assertIn("x.to(device='cpu', dtype=torch.float32)", self.video_source)
        self.assertIn("del inputs", self.video_source)
        self.assertNotIn("torch.float16", self.video_source)
        self.assertNotIn(".half()", self.video_source)

    def test_laptop_safe_batch_and_worker_defaults_are_explicit(self):
        for setting in (
            "'data.video_feature.image.batch_size': 1",
            "'data.batch_size': 1",
            "'data.num_workers': 0",
        ):
            self.assertIn(setting, self.video_source)
        for setting in (
            "tribe.data.batch_size = 1",
            "tribe.data.num_workers = 0",
            "tribe.data.video_feature.image.batch_size = 1",
        ):
            self.assertIn(setting, self.local_source)

    def test_feature_selection_is_passed_to_the_frozen_config(self):
        self.assertIn("features_to_use=None", self.video_source)
        self.assertIn("config_update['data.features_to_use'] = list(features_to_use)", self.video_source)
        self.assertIn("features_to_use=features_to_use", self.local_source)

    def test_local_modalities_and_shared_grid_contracts_are_retained(self):
        self.assertIn("tribe.data.audio_feature.device = 'cpu'", self.local_source)
        self.assertIn("tribe.data.video_feature.image.device = device", self.local_source)
        self.assertIn("'data.video_feature.frequency': 2.0", self.video_source)
        self.assertIn("model.lock", self.local_source)

    def test_documentation_names_tradeoffs_and_unmeasured_limits(self):
        for phrase in (
            "backend='pread'",
            "feature batch size 1",
            "zero\ndata-loader workers",
            "compact result",
            "guarded real-device measurement",
        ):
            self.assertIn(phrase, self.readme)


if __name__ == "__main__":
    unittest.main()
