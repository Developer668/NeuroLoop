"""Offline smoke checks and conservative surface-compatibility inspection."""
import gc
import json
import tarfile
from pathlib import Path
import nibabel as nib
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer, AutoFeatureExtractor, AutoImageProcessor

ROOT = Path(__file__).resolve().parent

def main():
    torch.set_num_threads(6)
    results = {}
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    text_path = ROOT / 'text/llama-3.2-3b-unsloth-q4'
    tokenizer = AutoTokenizer.from_pretrained(text_path, local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(text_path, local_files_only=True, trust_remote_code=False,
                                     device_map={'': device}, dtype=torch.bfloat16)
    inputs = tokenizer('A person watches a short advertisement.', return_tensors='pt').to(device)
    with torch.inference_mode():
        out = model(**inputs, output_hidden_states=True, use_cache=False)
    assert len(out.hidden_states) == 29 and out.last_hidden_state.shape[-1] == 3072
    assert torch.isfinite(out.last_hidden_state).all()
    results['llama_q4'] = {'passed': True, 'shape': list(out.last_hidden_state.shape), 'hidden_states': 29,
                          'quantized_4bit': bool(getattr(model, 'is_loaded_in_4bit', False))}
    assert results['llama_q4']['quantized_4bit']
    del model, out, inputs
    gc.collect(); torch.cuda.empty_cache()
    print('Llama Q4 passed', flush=True)
    for key, folder in [('w2v_bert', 'audio/w2v-bert-2.0'), ('dinov2', 'vision/dinov2-large')]:
        path = ROOT / folder
        model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False).to(device).eval()
        if key == 'w2v_bert':
            processor = AutoFeatureExtractor.from_pretrained(path, local_files_only=True)
            inputs = processor(np.zeros(16000, dtype=np.float32), sampling_rate=16000, return_tensors='pt').to(device)
        else:
            processor = AutoImageProcessor.from_pretrained(path, local_files_only=True)
            inputs = processor(images=np.zeros((224,224,3), dtype=np.uint8), return_tensors='pt').to(device)
        with torch.inference_mode():
            out = model(**inputs, output_hidden_states=True)
        assert torch.isfinite(out.last_hidden_state).all()
        assert out.last_hidden_state.shape[-1] == 1024
        results[key] = {'passed': True, 'shape': list(out.last_hidden_state.shape), 'hidden_states': len(out.hidden_states)}
        print(key, 'passed', flush=True)
        del model, out, inputs
        gc.collect(); torch.cuda.empty_cache()
    results['tsam'] = {}
    for name in ['backbone_weights.tar', 'tsam_weights.tar']:
        path = ROOT / 'emotion/tsam/weights' / name
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                members = archive.getmembers()
                results['tsam'][name] = {'format': 'tar archive', 'members': [{'name': m.name, 'bytes': m.size} for m in members],
                                        'status': 'inventory inspected, not extracted or executed'}
        else:
            # These two upstream checkpoints store NumPy scalar metadata.
            # Permit only the known NumPy scalar/dtype constructors, never arbitrary globals.
            globals_found = torch.serialization.get_unsafe_globals_in_checkpoint(path)
            assert set(globals_found) <= {'numpy.dtype', 'numpy.core.multiarray.scalar'}, globals_found
            with torch.serialization.safe_globals([
                (np._core.multiarray.scalar, 'numpy.core.multiarray.scalar'),
                np.dtype, np.dtypes.Float64DType,
            ]):
                ckpt = torch.load(path, weights_only=True, map_location='cpu')
            state = ckpt.get('state_dict', ckpt.get('model_state', ckpt))
            head_shapes = {f'last_fc.{k}': list(v.shape) for k, v in state.get('last_fc', {}).items()
                           if isinstance(v, torch.Tensor)}
            results['tsam'][name] = {'format': 'pytorch checkpoint', 'keys': list(ckpt),
                                    'status': 'weights_only load passed with explicit NumPy scalar/dtype allowlist',
                                    'head_shapes': head_shapes,
                                    'integration_status': 'Not integrated: both files contain composite TSAM state with an 8-output head; HF card describes 7 classes and a plain backbone.'}
            del ckpt
    patterns = []
    for emotion in ['amused', 'angry', 'content', 'fearful', 'neutral', 'sad', 'surprised']:
        entry = {'emotion': emotion, 'hemispheres': {}}
        for hemi in ['lh', 'rh', 'mesh']:
            path = next((ROOT / 'brain_readouts/kragel2015/source').glob(f'{hemi}.intensity*_{emotion}_*.gii'))
            gifti = nib.load(path)
            arrays = [a.data for a in gifti.darrays]
            assert all(np.isfinite(a).all() for a in arrays)
            entry['hemispheres'][hemi] = {'shapes': [list(a.shape) for a in arrays], 'intents': [int(a.intent) for a in gifti.darrays]}
        patterns.append(entry)
    results['kragel2015'] = {'directly_compatible': False, 'tribe_vertices_per_hemisphere': 10242,
                           'source_vertices_per_hemisphere': 32492, 'patterns': patterns,
                           'reason': 'Vertex counts differ; supplied mesh-named files contain scalar arrays, not coordinates/triangles. Surface registration and readout validation remain unresolved.'}
    (ROOT / 'verification.json').write_text(json.dumps(results, indent=2))
    (ROOT / 'brain_readouts/kragel2015/compatibility.json').write_text(json.dumps(results['kragel2015'], indent=2))
    print('Wrote verification.json', flush=True)

if __name__ == '__main__':
    main()
