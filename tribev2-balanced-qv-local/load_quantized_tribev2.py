"""Local INT8 SafeTensors loader. Does not execute Hugging Face repository code."""
import json
from pathlib import Path
import yaml
import numpy as np

import torch
from torch import nn
from torch.nn import functional as F
from safetensors.torch import load_file
from transformers import VJEPA2Config, VJEPA2Model, AutoVideoProcessor

ROOT = Path(__file__).resolve().parent


def resolve_device(device='auto'):
    if device != 'auto':
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA was requested but is unavailable on this machine')
        if device == 'mps' and (getattr(torch.backends, 'mps', None) is None or not torch.backends.mps.is_available()):
            raise RuntimeError('Apple MPS was requested but is unavailable on this machine')
        return device
    if torch.cuda.is_available():
        return 'cuda'
    if getattr(torch.backends, 'mps', None) is not None and torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'

class Int8Linear(nn.Module):
    """Keep weights INT8 and dequantize per forward on CPU/CUDA.

    This minimizes resident weight memory. On Apple MPS the INT8 buffers stay
    quantized between layers and only the active layer is reconstructed for the
    current forward pass, trading speed for a much lower unified-memory peak.
    """
    def __init__(self, in_features, out_features, bias):
        super().__init__()
        self.in_features, self.out_features = in_features, out_features
        self.register_buffer('qweight', torch.empty(out_features, in_features, dtype=torch.int8))
        self.register_buffer('scale', torch.empty(out_features, 1, dtype=torch.float32))
        self.register_buffer('bias', torch.empty(out_features, dtype=torch.bfloat16) if bias else None)

    def forward(self, x):
        weight = (self.qweight.to(torch.float32) * self.scale.float()).to(x.dtype)
        return F.linear(x, weight, self.bias.to(x.dtype) if self.bias is not None else None)

def load_video_model(repo_dir=ROOT, device='auto'):
    folder = Path(repo_dir) / 'quantized_video'
    device = resolve_device(device)
    metadata = json.loads((folder / 'quantization.json').read_text())
    if metadata['format'] != 'neuroloop-int8-v1':
        raise ValueError('Unsupported quantized format')
    config = VJEPA2Config.from_pretrained(folder, local_files_only=True)
    config._attn_implementation = 'sdpa'
    with torch.device('meta'):
        model = VJEPA2Model(config)
        for name, spec in metadata['linear_modules'].items():
            parent, _, child = name.rpartition('.')
            setattr(model.get_submodule(parent), child, Int8Linear(**spec))
    model.load_state_dict(load_file(folder / 'model.safetensors'), strict=True, assign=True)
    model = model.to(device).eval()
    processor = AutoVideoProcessor.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
    return model, processor

def load_quantized_tribev2(repo_dir=ROOT, device='auto', cache_folder=None):
    """Requires the official TRIBE package and its dependencies; lazy video injection."""
    from tribev2 import TribeModel
    from neuralset.extractors import video as video_module
    repo_dir = Path(repo_dir).resolve()
    device = resolve_device(device)
    cache_folder = str(cache_folder or repo_dir / 'cache-int8')
    # Convert the official Linux YAML tags without executing Python constructors.
    class SourceConfigLoader(yaml.SafeLoader):
        pass
    SourceConfigLoader.add_constructor('tag:yaml.org,2002:python/tuple',
                                      lambda loader, node: loader.construct_sequence(node))
    SourceConfigLoader.add_constructor('tag:yaml.org,2002:python/object/apply:pathlib.PosixPath',
                                      lambda loader, node: '/'.join(loader.construct_sequence(node)))
    config = yaml.load((repo_dir / 'config.yaml').read_text(), Loader=SourceConfigLoader)
    config['data']['study']['transforms']['chunkvideos']['infra']['folder'] = str(Path(cache_folder) / 'chunks')
    config['infra']['folder'] = str(repo_dir / 'runtime')
    runtime = repo_dir / 'runtime'
    runtime.mkdir(exist_ok=True)
    (runtime / 'config.yaml').write_text(yaml.safe_dump(config))
    original = video_module._HFVideoModel

    class LocalVideoModel(original):
        def __init__(self, model_name, pretrained=True, layer_type='', num_frames=None):
            if model_name != 'facebook/vjepa2-vitg-fpc64-256':
                super().__init__(model_name, pretrained, layer_type, num_frames)
                return
            if not pretrained:
                raise ValueError('Local INT8 loader only supports pretrained weights')
            self.model, self.processor = load_video_model(repo_dir, device)
            self.model_name, self.layer_type = model_name, layer_type
            self.num_frames = 64 if num_frames is None else num_frames
            if not 1 <= self.num_frames <= 64:
                raise ValueError('num_frames must be in [1, 64]')
            self.check_layer_type(layer_type, model_name)

        def predict(self, images, audio=None):
            if self.model_name != 'facebook/vjepa2-vitg-fpc64-256':
                return super().predict(images, audio)
            inputs = self.processor(videos=list(images), return_tensors='pt', do_rescale=True)
            video_module._fix_pixel_values(inputs)
            inputs = inputs.to(device=self.model.device, dtype=torch.bfloat16)
            with torch.inference_mode():
                return self.model(**inputs, output_hidden_states=True, skip_predictor=True)

        def predict_hidden_states(self, images, audio=None):
            if self.model_name != 'facebook/vjepa2-vitg-fpc64-256':
                return super().predict_hidden_states(images, audio)
            inputs = self.processor(videos=list(images), return_tensors='pt', do_rescale=True)
            video_module._fix_pixel_values(inputs)
            pixel_values = inputs['pixel_values_videos'].to(
                device=self.model.device, dtype=torch.bfloat16
            )
            encoder = self.model.encoder
            # Transformers records 41 V-JEPA2 states: embedding output plus each of
            # 40 encoder blocks. Neuralset's configured cache_n_layers=20 keeps these
            # exact equidistant indices before token mean pooling. Reproduce that
            # contract directly so the other 21 full token tensors never stay alive.
            state_count = len(encoder.layer) + 1
            keep = 20
            selected = [int(round(x)) for x in np.linspace(0, state_count - 1, keep)]
            wanted = set(selected)
            pooled = []
            with torch.inference_mode():
                hidden = encoder.embeddings(pixel_values)
                if 0 in wanted:
                    pooled.append(hidden.mean(dim=1, keepdim=True))
                for layer_index, layer in enumerate(encoder.layer, start=1):
                    hidden = layer(hidden, None)[0]
                    if layer_index in wanted:
                        # Neuralset immediately applies token_aggregation='mean'.
                        # Keeping a singleton token dimension makes its later mean a
                        # no-op while preserving the expected B x L x tokens x D API.
                        pooled.append(hidden.mean(dim=1, keepdim=True))
            if len(pooled) != keep:
                raise RuntimeError(f'Expected {keep} selected V-JEPA2 layers, got {len(pooled)}')
            return torch.stack(pooled, dim=1)

    # Neuralset constructs video wrappers lazily during feature extraction.
    video_module._HFVideoModel = LocalVideoModel
    tribe = TribeModel.from_pretrained(
        runtime, checkpoint_name='../best.ckpt', device=device, cache_folder=cache_folder,
        config_update={'data.video_feature.frequency': 2.0,
                       # Apple unified memory is the limiting resource on the local Mac.
                       # Batch size changes only feature-extraction batching, not sampling
                       # frequency, model weights, or the resulting feature contract.
                       'data.video_feature.image.batch_size': 1 if device == 'mps' else 4})
    # TRIBE concatenates modalities at identical time indices. Keep the official
    # 2 Hz shared grid; video-only 1.5 Hz produces 150 vs 200 samples per segment.
    return tribe

if __name__ == '__main__':
    model, _ = load_video_model()
    print('Loaded local INT8 V-JEPA2:', model.config.hidden_size, 'hidden dimensions on', model.device)
