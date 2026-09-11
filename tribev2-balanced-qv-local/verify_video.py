"""Offline weight-integrity and full-size synthetic clip regression check."""
import gc
import json
import torch
from transformers import VJEPA2Model
from load_quantized_tribev2 import ROOT, Int8Linear, load_video_model
from quantize_video import sha256

def main():
    torch.manual_seed(42)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    frames = 64 if device == 'cuda' else 2
    pixels = torch.rand(1, frames, 3, 256, 256, device=device, dtype=torch.bfloat16)
    with torch.inference_mode():
        base = VJEPA2Model.from_pretrained(
            ROOT / 'source_video', local_files_only=True, dtype=torch.bfloat16,
            attn_implementation='sdpa').to(device).eval()
        reference = base(pixel_values_videos=pixels, output_hidden_states=True, skip_predictor=True)
        expected = torch.stack([x.float().mean(dim=1).cpu() for x in reference.hidden_states])
        del reference, base
        gc.collect()
        if device == 'cuda':
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        model, processor = load_video_model(device=device)
        actual = model(pixel_values_videos=pixels, output_hidden_states=True, skip_predictor=True)
        measured = torch.stack([x.float().mean(dim=1).cpu() for x in actual.hidden_states])
        assert torch.isfinite(measured).all()
        assert measured.shape == expected.shape
        cosine = torch.nn.functional.cosine_similarity(expected.double().flatten(), measured.double().flatten(), dim=0).item()
        assert cosine > 0.98, f'Synthetic feature cosine too low: {cosine}'
        metadata = json.loads((ROOT / 'quantized_video/quantization.json').read_text())
        assert sha256(ROOT / 'quantized_video/model.safetensors') == metadata['quantized_sha256']
        report = {'passed': True, 'test': 'seed-42 synthetic clip; not an fMRI accuracy evaluation',
                  'input_shape': list(pixels.shape), 'pooled_hidden_shape': list(measured.shape),
                  'pooled_feature_cosine_similarity': cosine,
                  'relative_pooled_feature_rmse': float((expected-measured).square().mean().sqrt()/expected.square().mean().sqrt()),
                  'int8_linear_layers': sum(isinstance(m, Int8Linear) for m in model.modules()),
                  'device': device, 'torch': torch.__version__,
                  'cuda_peak_allocated_bytes': torch.cuda.max_memory_allocated() if device == 'cuda' else None}
        (ROOT / 'verification.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__':
    main()
