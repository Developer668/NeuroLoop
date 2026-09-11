# Local TRIBE v2 balanced video quantization

Additional text/audio/image models are now downloaded under `D:\NeuroLoop\models`.
See `../models/README.md` and use `../models/load_local_tribe.py` to select them.
The base loader below still describes the original video-only package.

Built locally from **Meta's official weights only**. No code, checkpoints, or
compiled Python from Jessylg27 were used. That repository's public README and JSON
metadata were read to identify its intended profile; this is not a malware verdict.

This independent build follows the same scope: original TRIBE brain checkpoint,
INT8 V-JEPA2 ViT-G video backbone, 2 Hz video sampling (corrected to match audio/text),
and 64 frames per clip. Audio and text are unchanged and are **not bundled**.
The laptop-safe defaults are feature batch size 1, dataset batch size 1, and zero
data-loader workers. This reduces prefetch and intermediate tensor pressure at the
cost of throughput; it does not change checkpoint, feature, or output shapes.
Neuralset 0.0.2 processes native video clips individually.

## Contents and source

- `best.ckpt`: unchanged official TRIBE checkpoint (about 709 MB).
- `config.yaml`, `LICENSE`: unchanged official TRIBE files.
- `quantized_video/model.safetensors`: **1,039,943,688 bytes**, down from
  4,138,311,608 bytes (about 75% smaller video weights).
- `source_video/`: retained official video originals for reproduction/comparison.
- `provenance.json`: pinned TRIBE revision and verified hashes.
- `quantized_video/quantization.json`: pinned video revision, hashes, quantized
  module definitions, and per-layer weight error.
- `verification.json`, `integration-verification.json`: actual test results.
- `.venv/`: local runtime, sharing the existing system PyTorch installation.

Official sources:

- https://huggingface.co/facebook/tribev2/tree/f894e783020944dcd96e5568550afe2aa9743f9f
- https://huggingface.co/facebook/vjepa2-vitg-fpc64-256/tree/875c192b7b704b87d1e1d99345769632dd5f739a

Model weights retain Meta's CC-BY-NC-4.0 license; see `LICENSE`.

## Use on this computer

Open PowerShell:

```powershell
Set-Location D:\NeuroLoop\tribev2-balanced-qv-local
.\.venv\Scripts\python.exe .\load_quantized_tribev2.py
```

This loads the quantized video model without requesting audio/text weights.
For the full pipeline, use this folder as your Python working directory:

```python
from load_quantized_tribev2 import load_quantized_tribev2

model = load_quantized_tribev2(device="cuda")
events = model.get_events_dataframe(video_path=r"D:\path\to\video.mp4")
predictions, segments = model.predict(events=events)
```

Use the supplied loader: ordinary `TribeModel.from_pretrained()` does not know
this SafeTensors INT8 format. The adapter overrides Neuralset's private video
wrapper in the current Python process so lazy loading uses these local weights.
Use a fresh process for a different video quantization package.

Full video/audio/text inference still needs the official feature encoders and
other assets downloaded by TRIBE. The official Llama-3.2-3B text model requires
Hugging Face access approval/authentication. Full multimodal inference was not
tested and may exceed 12 GB VRAM; this is not a fully offline all-modalities bundle.

### Apple MPS memory behavior

When the installed SafeTensors runtime exposes its `pread` backend, the loader
reads the quantized video checkpoint directly onto MPS with `backend='pread'`.
That avoids the default mmap-backed file view plus a second CPU-to-MPS model copy
that can be costly in Apple Silicon unified memory. Older SafeTensors runtimes
fall back to the previous CPU load followed by `model.to(device)`, preserving
compatibility rather than requiring a dependency upgrade.

The loader keeps the existing BF16 input path, INT8 linear weights, FP32 scales,
and CPU FP32 hidden-state output. It does not introduce a lower-precision model
or alter the checkpoint. Input frames are released immediately after the forward
pass, but the full hidden-state tuple is still produced by V-JEPA and converted
to CPU because that is the current Neuralset contract. Peak host RAM and native
MPS allocator behavior still require a guarded real-device measurement; the
model-free contract tests do not establish an end-to-end memory ceiling.

SafeTensors backend reference: https://github.com/safetensors/safetensors/blob/main/bindings/python/py_src/safetensors/torch.py

## Format and validation

Linear weights are prepared in BF16, then symmetrically quantized per output row
to signed INT8 using max-absolute scales. Scales remain FP32; other floating
weights use BF16. The loader dequantizes one linear layer at a time for ordinary
PyTorch matmuls. This reduces resident weight storage but does not promise a speedup.
It is an independent portable format, **not a byte-for-byte TorchAO export**.

No remote repository Python is executed by the video loader. Quantized tensors
use SafeTensors. The original TRIBE checkpoint is loaded with `weights_only=True`.
The adapter converts two known Linux YAML tags through a restricted loader into
a separate Windows-compatible `runtime/config.yaml`; the official files stay intact.

The 64-frame 256x256 synthetic GPU comparison measured pooled feature cosine
similarity 0.99999694 and relative RMSE 0.0024777 against official BF16 weights.
Peak allocated GPU memory in that isolated quantized test was about 2.28 GB.
This is a smoke/regression check, not a real-video benchmark or an fMRI accuracy
claim. See the JSON reports for exact scope and values.

## Reproduce / verify

```powershell
.\.venv\Scripts\python.exe .\download_official.py
.\.venv\Scripts\python.exe .\quantize_video.py
.\.venv\Scripts\python.exe .\verify_video.py
.\.venv\Scripts\python.exe .\verify_integration.py
```

The local runtime uses the existing PyTorch 2.11.0+cu128 and Transformers 5.13.0.
TRIBE's published PyTorch upper bound is older; this setup is tested for the checks
above, not every upstream workflow. Package versions are recorded in
`environment-freeze.txt`. The environment refers to the existing official source
checkout at `D:\NeuroLoop\tribev2-main`; keep that folder in place.

The original video files are retained, so total folder size is larger than the
quantized distribution. Large weights, environments, and caches are ignored by Git.

Multimodal correction: all modalities now retain TRIBE's shared 2 Hz grid. The earlier video-only 1.5 Hz setting was incompatible with multimodal concatenation. Video intermediates move to CPU before pooling; audio uses CPU in the application. Older JSON reports document their original test configuration; current application checks are under ../data/verification.
