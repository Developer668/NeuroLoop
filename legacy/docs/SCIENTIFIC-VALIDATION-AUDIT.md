# Scientific validation audit

September 11, 2026. This audit checks provenance and metadata. It does not report a newly reproduced accuracy or calibrated emotion probability.

## TSAM class mapping

The pinned upstream implementation (`gmontana/DecodingViewerEmotions`, revision `890540450e9459b9f917b2c50204b5be6fe72433`) lists:

`Anger, Contempt, Disgust, Fear, Happiness, Neutral, Sadness, Surprise`

The local adapter uses that order. The checkpoint's final weight has shape `[8, 2048]` and bias `[8]`. The public dataset labels are 0–7. The [Hugging Face model card](https://huggingface.co/dnamodel/tsam-viewer-emotions) instead describes seven classes and omits Neutral. This discrepancy must be resolved using checkpoint-specific training provenance; seven-class prose must not silently relabel an eight-output checkpoint.

The checkpoint includes epoch 7 and `best_score balanced: 0.4674041240897998`. That is saved training metadata, **not a metric reproduced by NeuroLoop**. Strict loading and the recorded Windows CPU forward pass establish execution only. See [actual forward-pass evidence](FRESH-EXECUTION.md).

## Published split audit

Reproduce with `.runtimes/app/Scripts/python.exe -X utf8 scripts/audit_tsam_dataset.py`. Results and exact source hashes are saved in `artifacts/scientific-audit/tsam/report.json`.

The three metadata CSVs were downloaded from [ADCUMEN](https://huggingface.co/datasets/dnamodel/adcumen-viewer-emotions), pinned revision `8296612414ce100b773b60f070706c5aa7ee8983`.

| Split | Rows | Unique video IDs | Invalid labels/timestamps |
|---|---:|---:|---:|
| Training | 21,392 | 5,659 | 0 |
| Validation | 2,856 | 725 | 0 |
| Testing | 2,387 | 660 | 0 |

No video ID or identical video/start-time pair overlaps between these three CSV splits. This does not check audiovisual near-duplicates, uploader/campaign overlap, missing media, training augmentations or what the supplied checkpoint actually saw.

The HF validation/test membership does not match the original repository's corresponding validation lists in this audit. Their IDs also did not overlap the inspected original training list. These facts are not proof of contamination; they mean that checkpoint-specific held-out membership has not been established. Obtain an authoritative mapping before publishing reproduced test performance.

## What is required to finish TSAM validation

1. Bind the exact checkpoint hash to its class order, preprocessing, training and evaluation split manifests.
2. Obtain the original evaluation media with permission; verify decoded content and hashes against the manifests. CSVs alone cannot be fed through an audiovisual model.
3. Reproduce preprocessing and report balanced accuracy, macro-F1, per-class recall and a confusion matrix on the bound evaluation split, with missing/unavailable clips counted explicitly.
4. Audit near-duplicates and source/campaign overlap, not only filenames.
5. For the intended ad domain, collect independent viewer labels with permission. The user currently does not know of an available labeled set. Model-generated labels cannot substitute.
6. Fit calibration on a separate calibration partition, freeze it, then report held-out calibration error and proper scoring metrics. Do not calibrate and report on the same clips.

Until then, the UI's softmax bars are relative evidence at temperature 1. They are not emotion intensity or measured probabilities. Original signed logits remain visible.

## Kragel registration and transfer

Real source volumes and a diagnostic projection are present. The complete surface-RAS-to-volume coordinate chain has not been established. A generic MNI305-to-MNI152 matrix cannot replace the original surface subject's volume geometry and registration.

Required provenance includes the matching source geometry, `orig.mgz` geometry, `talairach.xfm`, transforms between surface RAS and scanner RAS, target template identity, map-space compatibility, software versions and hashes. The chain involving `TalXFM @ Norig @ inverse(Torig)` must be justified for the actual assets, followed by any verified target-space transform. The published maps' target template must also match; a generic template name is insufficient.

Then reproduce reference scoring and evaluate transfer on independent stimulus-aligned measured fMRI and TRIBE predictions. Current cortical-subset spatial correlations are not automatically equivalent to the original whole-brain classifier. Finite scores, a visually plausible brain and full sampling coverage cannot close this gate. See [complete registration requirements](KRAGEL-REGISTRATION.md).

Kragel remains diagnostic and excluded from optimization decisions. A zero Kragel weight in combined evidence means it is not an eligible source, not that a viewer has zero emotion.

## Quantization and permissions

Original-versus-quantized validation requires identical representative held-out inputs and preprocessing, paired cortical outputs, per-modality error/correlation metrics and decision-agreement tests under predeclared tolerances. No new paired accuracy result is claimed here.

Commercial clearance remains unresolved. The TSAM model card directs commercial licensing inquiries to `ventures@warwick.ac.uk` and scientific inquiries to `g.montana@warwick.ac.uk`. Review the actual licenses for TRIBE, every encoder, TSAM, Kragel assets and evaluation media before the intended use. No permission request was sent and no rights were inferred from successful downloading.

Suggested scientific inquiry: “Please confirm the exact eight-class index order, preprocessing and train/validation/test video manifests for checkpoint SHA-256 f3a5e228ef12e9b9bf19116928392e8ed486f2d1908fea5c93e9452c62841569. The model card lists seven classes while the implementation and head have eight. Which evaluation media and protocol reproduce this checkpoint's reported result?”

Suggested licensing inquiry: describe the intended local ad-research workflow, whether commercial use is planned, what outputs are shown and whether weights/media are redistributed; request written permission covering that exact use.
