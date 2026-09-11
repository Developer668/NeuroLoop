# NeuroLoop model inventory

Downloaded and checked on this computer. All new download manifests pin upstream
revisions and verify SHA-256 for large files / Git blob hashes for small files.

| Component | Local folder | Size of selected downloads | Status |
|---|---|---|---|
| Llama-3.2-3B base, Unsloth NF4/Q4 | `text/llama-3.2-3b-unsloth-q4` | 2.26 GB | GPU forward and Neuralset text-loader checks passed |
| Meta Wav2Vec-BERT 2.0 | `audio/w2v-bert-2.0` | 2.32 GB | GPU audio forward passed |
| Meta DINOv2-large | `vision/dinov2-large` | 1.22 GB | GPU image forward passed; inactive in current TRIBE config |
| Meta V-JEPA2 ViT-G original | `vision/vjepa2-vitg-fpc64-256` | 4.14 GB already present | Directory junction reuses earlier official download |
| Local V-JEPA2 INT8 | `vision/vjepa2-vitg-int8` | 1.04 GB already present | Directory junction reuses earlier tested quantization |
| TSAM | `emotion/tsam/weights` | 377 MB | Strict eight-class CPU inference integrated; experimental, opt-in |
| Kragel 2015 | `brain_readouts/kragel2015/source` | About 7 MB | Seven patterns retained as sources; NOT a compatible readout yet |

Sizes are decimal GB and exclude environments/caches. The original TRIBE brain
weights and video loader remain in `../tribev2-balanced-qv-local`. The junctions
are links, not duplicate downloads; keep their original target folders in place.
`text/llama-3.2-3b-official` contains only the official reference configuration from
an access check, not a second full Llama download.

## Llama selection and local TRIBE use

Selected [Unsloth's base Llama-3.2-3B Q4](https://huggingface.co/unsloth/Llama-3.2-3B-bnb-4bit),
not the Instruct model. This is BitsAndBytes NF4 in SafeTensors, not GGUF. It exposes
29 hidden states of width 3072, matching the architecture expected by TRIBE.
BitsAndBytes 0.50.2 was installed only into the existing local `.venv`; the Unsloth
Python package is not needed. Q4 affects numerical features; compatibility checks
do not establish unchanged fMRI accuracy.

```powershell
Set-Location D:\NeuroLoop
.\tribev2-balanced-qv-local\.venv\Scripts\python.exe .\models\load_local_tribe.py
```

For a script run with that Python environment:

```python
from models.load_local_tribe import load_local_tribe

model = load_local_tribe(device="cuda")
events = model.get_events_dataframe(video_path=r"D:\path\to\advertisement.mp4")
predictions, segments = model.predict(events=events)
```

The helper selects the downloaded Q4 text and official audio weights plus the
existing local INT8 video encoder. DINOv2 stays available but inactive: the shipped
TRIBE configuration uses text/audio/video. Caches go to `D:\NeuroLoop\cache`.
The brain loader and actual Neuralset Q4 text loader were tested together.
Real video/audio/text/photo workflows have since run through the application, including local transcription. See `../docs/AUDIT.md` for current evidence. These checks do not establish arbitrary-input memory bounds or advertising accuracy.

## Kragel: compatibility gate remains closed

Only the requested [CANlab Kragel 2015 folder](https://github.com/canlab/Neuroimaging_Pattern_Masks/tree/107a4f18d80c0c2ea5ac0ae3ccf3398a80cad504/Multivariate_signature_patterns/2015_Kragel_emotionClassificationBPLS)
was selected: Amused, Angry, Content, Fearful, Neutral, Sad, Surprised. Original
hemisphere GIFTIs, matching volume files, mesh-named files, documentation and
license were retained; unrelated signatures were not downloaded.

All hemisphere patterns have 32,492 entries, versus TRIBE fsaverage5's 10,242 per
hemisphere (20,484 combined). The mesh-named GIFTIs contain 64,984 scalar values,
not coordinates/triangles. File format and vertex count do not establish surface
registration. Do not truncate, concatenate directly against TRIBE outputs, or
apply an unverified nearest-neighbor mapping. A verified registration/resampling
route and an evaluation of scoring/scaling are needed before this is a usable
emotion readout. These are bootstrap-statistic maps; they are not calibrated
emotion probabilities. `compatibility.json` records the inspection.

## TSAM: technical integration working, scientific validation pending

Both requested files from [the TSAM HF repository](https://huggingface.co/dnamodel/tsam-viewer-emotions)
are in `emotion/tsam/weights`. They are PyTorch checkpoint ZIPs despite their
`.tar` names. They were inspected using `weights_only=True` with only the known
NumPy scalar/dtype constructors explicitly allowed. No unrestricted pickle load
or upstream inference script was run.

The upstream inference source and instructions are in `emotion/tsam/source-code`,
pinned to commit `890540450e9459b9f917b2c50204b5be6fe72433`. Its dependencies are not
installed into the TRIBE environment. The HF card says seven output classes, but
both downloaded checkpoints actually contain a composite `model_state` with
`nn_X_input`, `nn_backbone`, and `last_fc`, whose weight shape is **[8, 2048]**.
The app adapter now loads the full checkpoint strictly and follows the pinned implementation's eight-class order, including Neutral. CPU inference on real video passed. Upstream card inconsistencies still require confirmation for scientific validation. TSAM is an independent prediction branch,
not a required component of TRIBE or a measurement of a particular viewer.

TSAM's included license permits academic research and non-commercial, non-clinical
evaluation; commercial use requires separate permission. TRIBE retains CC-BY-NC-4.0.
Other components retain their upstream terms; source model cards/licenses are saved.

## Verification and reproduction

- `verification.json`: individual GPU checks, TSAM inspection, Kragel shapes.
- `local-loader-verification.json`: TRIBE/Q4 text integration smoke check.
- `download-manifest.json` in each downloaded model folder: source and hashes.
- `../tribev2-balanced-qv-local/verification.json`: previous V-JEPA2 comparison.
- `download_assets.py`, `download_kragel.py`: pinned, selected-file downloads.
- `verify_assets.py`: repeat the checks with the local `.venv` Python.

## Application completion update

The repaired application uses a shared 2 Hz grid for video/audio/text; its video intermediates and audio encoder use CPU to reduce VRAM pressure. All four media integration cases passed in `../data/verification/modalities/report.json`. Earlier model-only reports are historical. Start the app using `../Start-NeuroLoop.cmd`; operational details are in `../README.md`. TSAM is integrated as an optional experimental CPU readout; Kragel remains blocked. Current architecture, dependency findings and actual-output receipts are in `../docs/AUDIT.md`.
