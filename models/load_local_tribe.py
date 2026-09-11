"""TRIBE configured to use the downloaded text/audio/image assets and local INT8 video."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'tribev2-balanced-qv-local'))
from load_quantized_tribev2 import load_quantized_tribev2
from neuroloop.device import resolve_device

def load_local_tribe(device='auto'):
    device=resolve_device(device)
    from neuroloop.checkpoints import validate_shards
    for folder in ('text/llama-3.2-3b-unsloth-q4','audio/w2v-bert-2.0','vision/dinov2-large'):
        validate_shards(ROOT/folder)
    tribe = load_quantized_tribev2(device=device, cache_folder=str(ROOT.parent / 'cache' / ('tribe-local-q4-int8-'+__import__('hashlib').sha256((ROOT.parent/'infrastructure/runtime/model.lock').read_bytes()).hexdigest()[:12])))
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
