# NeuroLoop model inventory

This checkout intentionally excludes model weights and vendor source trees. The
table is an install/readiness contract, not proof that files are present or
validated on the current machine. The authenticated capability response checks
the actual paths at runtime; it is the source of truth.
For the optional branches, `missing_weights`/`missing_assets` mean unavailable;
the installed-path status strings only mean that required paths exist, never that
the readout is scientifically validated.

| Component | Local folder | Size of selected downloads | Status |
|---|---|---|---|
| Llama-3.2-3B base, Unsloth NF4/Q4 | `text/llama-3.2-3b-unsloth-q4` | 2.26 GB expected | Runtime-local dependency; not supplied in this checkout |
| Meta Wav2Vec-BERT 2.0 | `audio/w2v-bert-2.0` | 2.32 GB expected | Runtime-local dependency; not supplied in this checkout |
| Meta DINOv2-large | `vision/dinov2-large` | 1.22 GB expected | Optional/inactive dependency; not supplied in this checkout |
| Meta V-JEPA2 ViT-G original | `vision/vjepa2-vitg-fpc64-256` | 4.14 GB expected | Runtime-local dependency; not supplied in this checkout |
| Local V-JEPA2 INT8 | `vision/vjepa2-vitg-int8` | 1.04 GB expected | Runtime-local dependency; not supplied in this checkout |
| TSAM | `emotion/tsam/weights` plus pinned source tree | 377 MB expected | Missing; install later, then perform strict technical and scientific checks |
| Kragel 2015 | `brain_readouts/kragel2015/source` | About 7 MB expected | Missing; install later, then establish registration/scoring validity |

Sizes are expected decimal GB and exclude environments/caches. The application
expects the original TRIBE brain checkpoint and video loader under
`../tribev2-balanced-qv-local`, but those runtime-local files are not tracked
here. Junctions, if created in a deployment, are links rather than evidence that
the target files are available. `text/llama-3.2-3b-official` is only an optional
reference configuration when supplied, not a full Llama download.

## Llama selection and local TRIBE use

The intended text dependency is [Unsloth's base Llama-3.2-3B Q4](https://huggingface.co/unsloth/Llama-3.2-3B-bnb-4bit),
not the Instruct model. It is BitsAndBytes NF4 in SafeTensors, not GGUF, and is
expected to expose 29 hidden states of width 3072 for the TRIBE adapter. Install
the model runtime and dependencies separately; Q4 affects numerical features,
and compatibility checks do not establish unchanged fMRI accuracy.

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

The helper can receive a `features_to_use` subset (`text`, `audio`, and/or `video`)
from the application. The application selects Q4 text for timed words, official
audio for an audio stream, and INT8 video for a visual stream; inactive encoders
are not prepared and therefore do not become resident for that run. DINOv2 stays
optional and inactive for the shipped checkpoint: its direct image feature key is
not present in the checkpoint's compatible projector set. Images use the explicit
repeated-frame video presentation instead. Caches are deployment configuration,
not repository assets. These checks do not establish arbitrary-input memory bounds
or advertising accuracy.

## Kragel: compatibility gate remains closed

No Kragel source or pattern files are present in this checkout. The later install
target is the requested [CANlab Kragel 2015 folder](https://github.com/canlab/Neuroimaging_Pattern_Masks/tree/107a4f18d80c0c2ea5ac0ae3ccf3398a80cad504/Multivariate_signature_patterns/2015_Kragel_emotionClassificationBPLS)
with the seven intended patterns: Amused, Angry, Content, Fearful, Neutral, Sad,
and Surprised. Do not treat a download, filename, or source hash as a validated
TRIBE-compatible readout.

The upstream surface files are expected to have 32,492 entries per hemisphere,
versus TRIBE fsaverage5's 10,242 per hemisphere (20,484 combined). The mesh-named
GIFTIs are scalar arrays, not coordinates/triangles. File format and vertex count
do not establish surface registration. Do not truncate, concatenate directly
against TRIBE outputs, or apply an unverified nearest-neighbor mapping. A verified
registration/resampling route and an evaluation of scoring/scaling are needed
before this is a usable emotion readout. These are bootstrap-statistic maps, not
calibrated emotion probabilities.

## TSAM: install-later integration, scientific validation pending

No TSAM checkpoint or pinned source tree is present in this checkout. The later
install target is [the TSAM HF repository](https://huggingface.co/dnamodel/tsam-viewer-emotions),
including `emotion/tsam/weights/tsam_weights.tar` and the source entrypoints
expected by the adapter. The runtime checks those paths before queueing an
optional readout; missing files are rejected rather than replaced with a fake or
partial result.

The intended upstream revision is `890540450e9459b9f917b2c50204b5be6fe72433`.
The adapter expects a composite checkpoint with `model_state` sections and the
source implementation's eight-class order, including Neutral; this must be
confirmed after the files are supplied. TSAM is an independent optional branch,
not a required component of TRIBE or a measurement of a particular viewer.

TSAM's included license permits academic research and non-commercial, non-clinical
evaluation; commercial use requires separate permission. TRIBE retains CC-BY-NC-4.0.
Other components retain their upstream terms; source model cards/licenses are saved.

## Verification and reproduction

- Any historical `verification.json`, loader report, or download manifest is
  evidence for that past environment only; it is not present-asset evidence for
  this checkout.
- `../tribev2-balanced-qv-local/verification.json`: previous V-JEPA2 comparison.
- `download_assets.py`, `download_kragel.py`: pinned, selected-file downloads.
- `verify_assets.py`: repeat the checks with the local `.venv` Python.

## Application completion update

The application retains a shared 2 Hz grid for video/audio/text and optional
readout integration points. TRIBE-only paths do not require TSAM or Kragel. The
optional branches remain unavailable until their files, dependencies, licensing
terms, and model-specific validation are supplied and recorded. Start-up and
operational details belong in `../README.md`; saved reports are historical unless
the current capability response confirms the corresponding paths.
