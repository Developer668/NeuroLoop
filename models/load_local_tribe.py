"""TRIBE configured to use the downloaded text/audio/image assets and local INT8 video."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'tribev2-balanced-qv-local'))
from load_quantized_tribev2 import load_quantized_tribev2
from neuroloop.device import resolve_device

def _configure_windows_cache_liveness():
    """Exca's POSIX signal-zero probe is not a Windows process existence check."""
    import os
    if os.name == 'nt':
        import psutil
        from exca.cachedict import inflight
        # Read-only OS process lookup; never signal another cached worker.
        inflight._is_pid_alive = psutil.pid_exists

def _configure_cpu_text_loading():
    """Pin NF4 loading to CPU before allocation, rather than moving it afterward."""
    from neuralset.extractors.text import HuggingFaceText
    original = HuggingFaceText._load_model
    if getattr(original, '_neuroloop_cpu_bound', False):
        return
    def load_on_cpu(self, **kwargs):
        if self.device == 'cpu':
            kwargs = {**kwargs, 'device_map': {'': 'cpu'}, 'local_files_only': True}
        model = original(self, **kwargs)
        if self.device == 'cpu' and any(p.device.type != 'cpu' for p in model.parameters()):
            raise RuntimeError('CPU text verification found a non-CPU model parameter')
        return model
    load_on_cpu._neuroloop_cpu_bound = True
    HuggingFaceText._load_model = load_on_cpu

def load_local_tribe(device='auto', features_to_use=None, cache_identity=None):
    """Load TRIBE with only the feature encoders selected for this input."""
    device=resolve_device(device)
    _configure_windows_cache_liveness()
    if device == 'cpu':
        _configure_cpu_text_loading()
    from neuroloop.checkpoints import validate_shards
    for folder in ('text/llama-3.2-3b-unsloth-q4','audio/w2v-bert-2.0','vision/dinov2-large'):
        validate_shards(ROOT/folder)
    import hashlib
    if cache_identity is None:
        from neuroloop.inference import profile_id
        cache_identity = profile_id()
    # Neuralset excludes device from its own extractor UID. Bind this outer
    # namespace to the complete verified model/processor/code manifest AND
    # actual device, including standalone loader callers.
    cache_contract = hashlib.sha256(f'{cache_identity}|{device}'.encode()).hexdigest()
    cache_folder = ROOT.parent / 'cache' / ('tribe-local-profile-' + cache_contract)
    tribe = load_quantized_tribev2(device=device, features_to_use=features_to_use, cache_folder=str(cache_folder))
    tribe.data.text_feature.model_name = str(ROOT / 'text/llama-3.2-3b-unsloth-q4')
    tribe.data.text_feature.device = 'accelerate' if device == 'cuda' else device
    tribe.data.audio_feature.model_name = str(ROOT / 'audio/w2v-bert-2.0')
    tribe.data.audio_feature.device = 'cpu'
    tribe.data.image_feature.image.model_name = str(ROOT / 'vision/dinov2-large')
    tribe.data.video_feature.image.device = device
    # Keep direct callers on the laptop-safe path too; the application applies
    # the same dataset settings after loading as a second line of defense.
    tribe.data.batch_size = 1
    tribe.data.num_workers = 0
    tribe.data.video_feature.image.batch_size = 1
    return tribe

if __name__ == '__main__':
    model = load_local_tribe()
    print('Local TRIBE configured. Active modalities:', model.data.features_to_use)
    print('Text:', model.data.text_feature.model_name)
    print('Audio:', model.data.audio_feature.model_name)
    print('Image (inactive):', model.data.image_feature.image.model_name)
    print('Video sampling:', model.data.video_feature.frequency)
