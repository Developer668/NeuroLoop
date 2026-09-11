"""Local INT8 SafeTensors loader. Does not execute Hugging Face repository code."""
import inspect
import json
from pathlib import Path
import yaml

import torch
from torch import nn
from torch.nn import functional as F
from safetensors.torch import load_file
from transformers import VJEPA2Config, VJEPA2Model, AutoVideoProcessor

ROOT = Path(__file__).resolve().parent


def _supports_safetensors_backend():
    """Return whether this SafeTensors runtime exposes an alternate I/O backend."""
    try:
        return 'backend' in inspect.signature(load_file).parameters
    except (TypeError, ValueError):
        # Keep compatibility with older/binary-wrapped SafeTensors releases.
        return False


def _load_video_state_dict(path, device):
    """Load video weights without a CPU-to-MPS duplicate when the runtime allows it.

    SafeTensors' ``pread`` backend avoids the mmap-backed file view that can remain
    resident in Apple Silicon's unified memory while a second MPS copy is built.
    Older runtimes retain the previous CPU load and explicit ``model.to(device)``
    path rather than changing the checkpoint or dtype contract.
    """
    if device == 'mps' and _supports_safetensors_backend():
        return load_file(path, device=device, backend='pread'), True
    return load_file(path, device='cpu'), False


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
    """Keep weights INT8, dequantize one layer at a time for portable CPU/CUDA inference.

    This saves resident weight memory; it is not a fused INT8 kernel or a speed promise.
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
    state_dict, loaded_on_device = _load_video_state_dict(folder / 'model.safetensors', device)
    model.load_state_dict(state_dict, strict=True, assign=True)
    # ``assign=True`` makes the module reference the loaded tensors. Drop the
    # temporary mapping before any fallback device copy so it adds no extra refs.
    del state_dict
    if not loaded_on_device:
        model = model.to(device)
    model = model.eval()
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
                result = self.model(**inputs, output_hidden_states=True, skip_predictor=True)
            # The processor inputs are no longer needed while the device-side
            # hidden states are copied to their required CPU representation.
            del inputs
            # Neuralset converts features to numpy, which does not support BF16.
            # Pooling in Neuralset happens on CPU. Do not hold or concatenate all
            # 41 FP32 token layers on the laptop GPU alongside text/audio models.
            result.hidden_states = tuple(x.to(device='cpu', dtype=torch.float32) for x in result.hidden_states)
            return result

    # Neuralset constructs video wrappers lazily during feature extraction.
    video_module._HFVideoModel = LocalVideoModel
    tribe = TribeModel.from_pretrained(
        runtime, checkpoint_name='../best.ckpt', device=device, cache_folder=cache_folder,
        config_update={'data.video_feature.frequency': 2.0,
                       'data.video_feature.image.batch_size': 1,
                       'data.batch_size': 1,
                       'data.num_workers': 0})
    # TRIBE concatenates modalities at identical time indices. Keep the official
    # 2 Hz shared grid; video-only 1.5 Hz produces 150 vs 200 samples per segment.
    return tribe

if __name__ == '__main__':
    model, _ = load_video_model()
    print('Loaded local INT8 V-JEPA2:', model.config.hidden_size, 'hidden dimensions on', model.device)
