# Model compatibility and interpretation

**Current recovery status:** GPU inference and Launch are paused after the later repeated 0x113 crash. The successful runs below are earlier compatibility evidence, not current stability clearance. See [current audit](AUDIT.md) and [remaining gates](REMAINING-WORK.md).

## TRIBE v2

The intended TRIBE configuration preserves the original Meta brain checkpoint,
uses the previously selected INT8 video encoder and NF4 base text encoder, and
introduces no Jessylg27 code or weights. These runtime-local model files are not
included in the current checkout; capability status is the source of truth for
their presence.

The earlier multimodal length mismatch was resolved by preserving the shared 2 Hz grid. Audio and video hidden-state pooling use CPU, and each neural evaluation runs in its own supervised child process. The new preflight refuses an already hot GPU (82°C or higher), less than 4 GiB free GPU memory, or less than 3 GiB free system RAM. PyTorch's 75% allocation limit, bounded execution, cancellation and non-replay recovery remain in place.

The latest September 10 real NASA video verification produced a finite 11 × 20,484 response at approximately 2.81 GiB peak PyTorch allocation. Real audio, photographic presentation, a second video and a controlled edit also completed. The first multi-candidate attempt exposed retained model memory; process exit now reclaims allocations before each subsequent candidate. See `data/verification/refinement/real-media-report.json`. This is not total driver memory or a guarantee for arbitrary input lengths. The original Windows `0x113` graphics-kernel failure remains undiagnosed; the dump was not accessible. No graphics drivers, registry values, firmware or power settings were changed.

Source: [Meta's TRIBE model card](https://huggingface.co/facebook/tribev2), local pinned source and inference reports.

## TSAM: install-later integration contract

The current checkout does not contain the TSAM checkpoint or its pinned source
tree. `backend/neuroloop/tsam.py` retains a strict CPU-only adapter, but no TSAM
asset is present or validated here. The capability response reports the missing
paths, and a request that selects TSAM is rejected before a run is queued until
all required files are supplied.

The expected install includes `models/emotion/tsam/weights/tsam_weights.tar`, the
pinned source revision `890540450e9459b9f917b2c50204b5be6fe72433`, and the source
entrypoints used by the adapter. After installation, verify the checkpoint's
composite `model_state` strictly, confirm the eight-class order **Anger, Contempt,
Disgust, Fear, Happiness, Neutral, Sadness, Surprise**, and reproduce the
published preprocessing before recording any new compatibility evidence. A model
file or successful load alone is not scientific validation on advertisements.

The intended readout is independent CPU audiovisual evidence, opt-in with an
explicit research-use acknowledgement. Any future logits must remain signed,
uncalibrated, and separate from TRIBE; response-target use may only go through the
explicit versioned ensemble. The upstream research/non-commercial/non-clinical
license and any later permission must be checked before redistribution or
commercial use.

Sources: [TSAM checkpoint card](https://huggingface.co/dnamodel/tsam-viewer-emotions)
and [original implementation](https://github.com/gmontana/DecodingViewerEmotions).
Any older verification report is historical and is not evidence that this checkout
contains the assets.

When those assets are installed, the adapter is configured for 12 RGB segments,
one three-channel mel-spectrogram segment, non-overlapping five-second windows,
10 FPS extraction, 256-pixel video height, and the upstream 224-pixel transform.
It preserves source audio rate and reports incomplete tails rather than inventing
coverage. These are implementation contracts, not evidence that TSAM is currently
installed or accurate on advertisements.

## Anatomy: working

The Destrieux atlas fetched through Nilearn is explicitly provided on fsaverage5. Both hemisphere label arrays contain 10,242 vertices. The application summarizes 148 anatomical parcels in the same left/right order as TRIBE, without inferring emotion or psychological function. Parcel means, cortical timelines, and compatible response-difference overlays are derived from saved numerical arrays.

Source: [Nilearn's surface Destrieux atlas documentation](https://nilearn.github.io/stable/modules/generated/nilearn.datasets.fetch_atlas_surf_destrieux.html). Reproduce with `scripts/prepare_atlas.py`. The installed atlas is `data/geometry/atlas.json`; source annotation files are under `models/brain_readouts/anatomy`.

## Kragel: install-later compatibility gate

The current checkout does not contain the seven Kragel source volume pairs. The
TRIBE-derived adapter is inactive; its capability status is
`missing_assets`, and selecting Kragel is rejected before queueing until the
expected volumes and fsaverage5 geometry are present. No Kragel asset is claimed
as downloaded, registered, or validated here.

The later install must provide the published MNI volume maps for Amused, Angry,
Content, Fearful, Neutral, Sad, and Surprised, together with the required geometry.
The 32,492-value surface files cannot be resized or index-interpolated onto
TRIBE's 10,242 vertices per hemisphere. Before activation, document a verified
registration/projection route, medial-wall handling, scoring and normalization,
source hashes, reference-score reproduction, and held-out transfer results.

The inactive adapter implements an explicit volume-to-surface projection contract:
inverse-affine sampling at five points from white to pial, left/right fsaverage5
ordering, finite-value coverage checks, and provenance hashes. It does not resize
or index-interpolate the 32,492-value surface files. These safeguards are retained
so installation can be validated later; they do not make the missing maps available.

Even after those checks, pattern-expression values are not emotion probabilities
or observed viewer responses. Preserve CANlab/upstream research and licensing
terms and keep this branch distinct from direct-media TSAM output.

Source: [CANlab's pattern description](https://github.com/canlab/Neuroimaging_Pattern_Masks/blob/master/Multivariate_signature_patterns/2015_Kragel_emotionClassificationBPLS/contents_description.md).
The local path is an install target, not present-asset evidence.

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
omits uncovered tails; it never substitutes whole-creative or another-segment values.
