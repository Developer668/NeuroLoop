"""Local INT8 SafeTensors loader. Does not execute Hugging Face repository code."""
import inspect
import hashlib
import json
from pathlib import Path
import yaml

import torch
from torch import nn
from torch.nn import functional as F
from safetensors.torch import load_file
from transformers import VJEPA2Config, VJEPA2Model, AutoVideoProcessor

ROOT = Path(__file__).resolve().parent

def _static_video_key(images):
    """Only identical decoded frames qualify for exact feature reuse."""
    import numpy as np
    if images.ndim != 4 or not len(images):
        return None
    if not all(np.array_equal(frame, images[0]) for frame in images[1:]):
        return None
    return (images.shape, str(images.dtype), hashlib.sha256(images[0].tobytes()).hexdigest())


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


def _compact_hidden_states(hidden_states, cache_n_layers=20):
    """Preserve Neuralset's layer subselection; pool only the token dimension.

    The checkpoint consumes TWO group means from the 20 selected layers.
    Pooling tokens on-device is equivalent to the downstream mean, while
    collapsing layer groups here would change its 2,816-feature contract.
    """
    import numpy as np
    states = tuple(hidden_states or ())
    if not states:
        raise RuntimeError('V-JEPA returned no hidden states')
    indices = range(len(states))
    if cache_n_layers is not None and cache_n_layers < len(states):
        indices = [int(round(x)) for x in np.linspace(0, len(states) - 1, cache_n_layers)]
    return tuple(states[index].to(dtype=torch.float32).mean(dim=-2, keepdim=True)
                 for index in indices)


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

def load_quantized_tribev2(repo_dir=ROOT, device='auto', cache_folder=None, features_to_use=None):
    """Requires the official TRIBE package and its dependencies; lazy video injection."""
    from tribev2 import TribeModel
    from neuralset.extractors import video as video_module
    repo_dir = Path(repo_dir).resolve()
    device = resolve_device(device)
    if features_to_use is not None:
        features_to_use = tuple(features_to_use)
        allowed = {'text', 'audio', 'video'}
        if not features_to_use or any(feature not in allowed for feature in features_to_use):
            raise ValueError('features_to_use must be a non-empty subset of text, audio, and video')
        if len(set(features_to_use)) != len(features_to_use):
            raise ValueError('features_to_use must not contain duplicates')
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
        def predict_hidden_states(self, images, audio=None):
            # Repeated-frame image presentations feed precisely the same tensor
            # at every timestep. Reuse one actual frozen-model forward result,
            # never a response from a merely similar image or moving video.
            # This V-JEPA forward consumes only pixels; TRIBE's audio encoder
            # is a separate branch. Never apply this rule to an audio-aware model.
            key = _static_video_key(images) if self.model_name == 'facebook/vjepa2-vitg-fpc64-256' else None
            cached = getattr(self, '_static_features', None)
            if key is not None and cached is not None and cached[0] == key:
                return cached[1].clone()
            out = super().predict_hidden_states(images, audio)
            self._static_features = (key, out.detach().clone()) if key is not None else None
            return out

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
            # Preserve the 20 cached layers and both configured group means.
            # Pool tokens before host transfer to avoid retaining all 41
            # FP32 token layers alongside text/audio models.
            compacted = _compact_hidden_states(result.hidden_states)
            result.hidden_states = tuple(x.to(device='cpu', dtype=torch.float32) for x in compacted)
            del compacted
            # Neuralset consumes only ``hidden_states`` from this result. Drop
            # transformer output fields that otherwise retain device tensors
            # until the video event has finished pooling.
            for attribute in ('last_hidden_state', 'masked_hidden_state', 'attentions', 'predictor_output'):
                if hasattr(result, attribute):
                    setattr(result, attribute, None)
            return result

    # Neuralset constructs video wrappers lazily during feature extraction.
    video_module._HFVideoModel = LocalVideoModel
    config_update = {
        'data.video_feature.frequency': 2.0,
        'data.video_feature.image.batch_size': 1,
        'data.batch_size': 1,
        'data.num_workers': 0,
    }
    if features_to_use is not None:
        # The brain checkpoint retains projectors for all trained feature keys,
        # while Data only prepares the selected extractors. Missing modalities
        # are zero-filled by the frozen TRIBE model, so this is a safe loading
        # optimization rather than a checkpoint change.
        config_update['data.features_to_use'] = list(features_to_use)
    tribe = TribeModel.from_pretrained(
        runtime, checkpoint_name='../best.ckpt', device=device, cache_folder=cache_folder,
        config_update=config_update)
    # TRIBE concatenates modalities at identical time indices. Keep the official
    # 2 Hz shared grid; video-only 1.5 Hz produces 150 vs 200 samples per segment.
    return tribe

if __name__ == '__main__':
    model, _ = load_video_model()
    print('Loaded local INT8 V-JEPA2:', model.config.hidden_size, 'hidden dimensions on', model.device)
