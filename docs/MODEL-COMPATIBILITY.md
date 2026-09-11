# Model compatibility and interpretation

**Current recovery status:** GPU inference and Launch are paused after the later repeated 0x113 crash. The successful runs below are earlier compatibility evidence, not current stability clearance. See [current audit](AUDIT.md) and [remaining gates](REMAINING-WORK.md).

## TRIBE v2

The original Meta brain checkpoint remains unchanged. The local video encoder uses the previously created INT8 weights; the base text encoder uses NF4. No Jessylg27 code or weights were introduced by this redesign.

The earlier multimodal length mismatch was resolved by preserving the shared 2 Hz grid. Audio and video hidden-state pooling use CPU, and each neural evaluation runs in its own supervised child process. The new preflight refuses an already hot GPU (82°C or higher), less than 4 GiB free GPU memory, or less than 3 GiB free system RAM. PyTorch's 75% allocation limit, bounded execution, cancellation and non-replay recovery remain in place.

The latest September 10 real NASA video verification produced a finite 11 × 20,484 response at approximately 2.81 GiB peak PyTorch allocation. Real audio, photographic presentation, a second video and a controlled edit also completed. The first multi-candidate attempt exposed retained model memory; process exit now reclaims allocations before each subsequent candidate. See `data/verification/refinement/real-media-report.json`. This is not total driver memory or a guarantee for arbitrary input lengths. The original Windows `0x113` graphics-kernel failure remains undiagnosed; the dump was not accessible. No graphics drivers, registry values, firmware or power settings were changed.

Source: [Meta's TRIBE model card](https://huggingface.co/facebook/tribev2), local pinned source and inference reports.

## TSAM: technically working, experimental

The downloaded `tsam_weights.tar` is a PyTorch ZIP checkpoint with nested `model_state` sections: `nn_X_input`, `nn_backbone`, and `last_fc`. It is not a plain ResNet state dictionary. The separate backbone file is not needed when every layer of the final checkpoint is loaded strictly.

`backend/neuroloop/tsam.py` constructs the original architecture, avoids the upstream permissive backbone loader, and requires an exact state-dictionary match. Loading uses `weights_only=True` with a narrow allowlist for the NumPy scalar metadata present in the checkpoint. It never falls back to random or partial weights.

The checkpoint has eight outputs. The original source's class order is **Anger, Contempt, Disgust, Fear, Happiness, Neutral, Sadness, Surprise**. The shorter list in the Hugging Face description omits Neutral. The adapter uses the source order, not the shorter list.

Inference follows the repository's default configuration: 12 RGB segments, one three-channel mel-spectrogram segment, complete non-overlapping five-second windows with a five-second stride, 10 FPS extraction, 256-pixel height and the upstream 224-pixel transform. Audio rate is retained; the three mel channels use 25/50/100 ms windows, 10/25/50 ms hops, 4,800-point FFTs, 224 mel bands, log(+1e-6), and 224×224 resizing. A short clip is `not_applicable`; an odd-duration clip omits only its incomplete tail and reports that tail explicitly. The training configuration is not embedded in the checkpoint, so this verifies strict technical compatibility with the published default inference setup, not recovery of an undocumented training configuration or accuracy on advertisements.

TSAM runs on CPU and reads the original audiovisual stimulus independently of TRIBE. It is opt-in through the run form with an explicit research-use acknowledgement. The UI preserves signed logits and window boundaries and labels them uncalibrated. In response-target mode, TSAM can contribute only through the explicit versioned ensemble while its raw output remains separate. Incomplete tails and inapplicable inputs are explicitly reported. A failed secondary readout does not invent replacement values.

Checkpoint SHA-256: `f3a5e228ef12e9b9bf19116928392e8ed486f2d1908fea5c93e9452c62841569`.

Source revision: `890540450e9459b9f917b2c50204b5be6fe72433`.

Sources: [TSAM checkpoint card](https://huggingface.co/dnamodel/tsam-viewer-emotions), [original implementation](https://github.com/gmontana/DecodingViewerEmotions). Reports: `data/verification/tsam-runtime/report.json` and `data/verification/redesign/evaluation.json`.

## Anatomy: working

The Destrieux atlas fetched through Nilearn is explicitly provided on fsaverage5. Both hemisphere label arrays contain 10,242 vertices. The application summarizes 148 anatomical parcels in the same left/right order as TRIBE, without inferring emotion or psychological function. Parcel means, cortical timelines, and compatible response-difference overlays are derived from saved numerical arrays.

Source: [Nilearn's surface Destrieux atlas documentation](https://nilearn.github.io/stable/modules/generated/nilearn.datasets.fetch_atlas_surf_destrieux.html). Reproduce with `scripts/prepare_atlas.py`. The installed atlas is `data/geometry/atlas.json`; source annotation files are under `models/brain_readouts/anatomy`.

## Kragel: experimental TRIBE decoder active

The seven published Kragel BPLS emotion signatures are now wired as an experimental
TRIBE-derived readout. NeuroLoop still does **not** resize or index-interpolate the
32,492-value surface scalar files onto TRIBE. Instead it uses the published MNI volume
maps and applies each volume's inverse affine to fsaverage5 world coordinates, sampling
five evenly spaced points from white (0.0) through pial (1.0) and averaging finite
samples. It concatenates left then right hemispheres, 10,242 vertices each, producing
the 20,484-value order used by TRIBE. Out-of-bounds and non-finite volume samples are
masked; coverage is reported and insufficient coverage fails closed. Source map hashes,
affine/orientation metadata, geometry hashes, projection version and cache identity are
persisted in evidence.

Each TRIBE time point is spatially centered, L2-normalized and compared with each
normalized Kragel signature. The resulting trajectories and aggregates are pattern
expression correlations, not emotion probabilities. The transfer from measured fMRI
signatures to TRIBE synthetic predictions remains scientifically unvalidated, so the
UI labels this source experimental and keeps it distinct from direct-media TSAM output.

Source: [CANlab's pattern description](https://github.com/canlab/Neuroimaging_Pattern_Masks/blob/master/Multivariate_signature_patterns/2015_Kragel_emotionClassificationBPLS/contents_description.md). Local inspection: `models/brain_readouts/kragel2015/compatibility.json`.

## Response contract and temporal targets

`response-ensemble/v1` preserves the fixed 0.55 TSAM / 0.45 Kragel profile. A source
that is unavailable is omitted and the remaining source is renormalized per supported
dimension; missing Kragel contempt/disgust signatures remain missing, not numeric zero.
Malformed labels, logits, trajectories, weights or non-finite values fail closed before
scoring. `response-target-distance/v1` is explicitly versioned and reports source
disagreement and provenance separately from the raw evidence.

Every active source carries model/checkpoint/preprocessing/geometry/projection metadata,
and the ensemble carries its own version and specification hash. Temporal rows use a
source-duration-normalized `[0,1]` axis. Target specs support the legacy whole-creative
emotion map, one normalized `time_window`, or multiple normalized `windows`. Scoring
uses only intervals overlapping the requested window, duration-weights overlaps, and
uses interval-union coverage so overlapping rows cannot inflate support. A target
segment with an uncovered gap, or a requested dimension supported for only part of the
segment, is not scoreable; it never substitutes whole-creative or another-segment
values. Source and per-dimension coverage remain visible in the temporal ensemble
series.
