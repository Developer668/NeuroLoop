"""Reproducible per-output-channel INT8 conversion of official Meta weights."""
import hashlib
import json
import shutil
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file
from transformers import VJEPA2Config, VJEPA2Model

ROOT = Path(__file__).resolve().parent

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    torch.set_num_threads(6)
    source = ROOT / 'source_video'
    output = ROOT / 'quantized_video'
    output.mkdir(exist_ok=True)
    expected = 'f205e77aa2ade168db6b09d4bc420d156141f64ab964278a9c181a2bdf2a232b'
    actual = sha256(source / 'model.safetensors')
    if actual != expected:
        raise RuntimeError('Official video weight SHA256 mismatch')
    config = VJEPA2Config.from_pretrained(source, local_files_only=True)
    with torch.device('meta'):
        model = VJEPA2Model(config)
    linears = {name: {'in_features': m.in_features, 'out_features': m.out_features,
                      'bias': m.bias is not None}
               for name, m in model.named_modules() if isinstance(m, torch.nn.Linear)}
    tensors, errors = {}, {}
    with safe_open(source / 'model.safetensors', framework='pt', device='cpu') as f:
        for key in f.keys():
            w = f.get_tensor(key)
            name = key.removesuffix('.weight')
            if key.endswith('.weight') and name in linears:
                # Match the reference approach's BF16 preparation, then symmetric INT8.
                w = w.to(torch.bfloat16).float()
                scale = w.abs().amax(dim=1, keepdim=True).clamp_min(1e-12) / 127
                q = (w / scale).round().clamp(-127, 127).to(torch.int8)
                tensors[name + '.qweight'] = q.contiguous()
                tensors[name + '.scale'] = scale.contiguous()
                errors[name] = float(((q.float() * scale - w).square().mean().sqrt()
                                      / w.square().mean().sqrt().clamp_min(1e-12)))
            else:
                tensors[key] = w.to(torch.bfloat16).contiguous() if w.is_floating_point() else w
    save_file(tensors, output / 'model.safetensors', metadata={'format': 'neuroloop-int8-v1'})
    for file in ['config.json', 'video_preprocessor_config.json']:
        shutil.copy2(source / file, output / file)
    metadata = {'format': 'neuroloop-int8-v1', 'source_repo': 'facebook/vjepa2-vitg-fpc64-256',
                'source_revision': '875c192b7b704b87d1e1d99345769632dd5f739a',
                'source_sha256': actual, 'quantization': 'symmetric per-row INT8 weight-only',
                'float_dtype': 'bfloat16', 'linear_modules': linears,
                'relative_weight_rmse': errors,
                'source_bytes': (source / 'model.safetensors').stat().st_size,
                'quantized_bytes': (output / 'model.safetensors').stat().st_size,
                'quantized_sha256': sha256(output / 'model.safetensors')}
    (output / 'quantization.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps({k: v for k, v in metadata.items() if k not in ['linear_modules', 'relative_weight_rmse']}, indent=2))
    print('Quantized linear layers:', len(linears), flush=True)

if __name__ == '__main__':
    main()
