# MeowStore research evidence verification

Verified against the live API and remote sponsor storage on September 13, 2026. This report covers video run `13f887ee-6096-4d47-8175-4dcff94fe1cf`, campaign `248a28aa-dc15-4d7b-9352-276cdfca710d`.

The real MiniMax H3 output is asset `a059ac8b-852d-4a26-9bff-578c692a1e88`, SHA-256 `781a41a29d4706130a0e7719efb459611c487ee89bf8f8ca7ba57d5e1d9abcbb`: five seconds, 1024×576, 24 fps, with audio. Each receipt below is linked to this exact asset and marked `campaign_loop`, rather than a separate diagnostic run.

| Stage | Persisted receipt | Actual result |
|---|---|---|
| GLM vision | `98c5f055-1aa2-45bf-8e6d-8592fcee998b` | Six sampled frames; generated media detected; visual quality proxy 0.82, text legibility proxy 0.62. |
| Faster Whisper Small | Within the vision receipt | CPU INT8, real audio transcription; no speech segments detected. This does not prove silence. |
| TSAM | `22986327-c873-4a78-956e-95fe0686ae34` | CPU inference, one five-second window of eight class logits. Highest logit: Happiness. These are not measured viewer emotions or calibrated probabilities. |
| TRIBE v2 | `514970a9-c013-4d76-969f-1aa1a66c4d09` | CUDA inference, Wav2Vec-BERT 2.0 audio encoder and V-JEPA2 INT8 video encoder; six rows × 20,484 cortical vertices. |
| GLM final summary | `e8b5d91a-8ddd-4d32-b171-605d0e10f950` | Completed summary grounded in the run evidence. |

The cortical artifact `57686d1e-3b3f-4346-8998-f92eafb407e8` downloaded successfully through the authenticated API. Its 456,767 bytes match SHA-256 `28f453d5892cc8bfe33b4b4a004ef6f4920d72eb045359665195a49b729702a0`. NumPy loaded it without pickle: `values` is finite float32 `[6, 20484]`, and `times` is finite float64 `[6]`. The cortical frame API returned HTTP 200 with actual values, range, time, and label.

The text encoder was inactive for this video. This run does not establish execution of LLaMA or DINO. TRIBE predicts a model response, not an individual's observed brain scan; quantized neuroscience accuracy is not established. Kragel spatial projection remains explicitly unverified and ineligible for decisions. The padded final cortical row is excluded from the diagnostic Kragel time support.

## Remote evidence

The [Weave snapshot](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/01a09c42-0cd7-7787-8992-9c4faa6ff9f4) was published and read back. A separate remote Dataset read confirmed the exact run, asset SHA, eligible candidate, and completed required evidence. The [W&B dashboard](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/runs/neuroloop-outcomes) export also confirmed persisted metrics remotely. W&B artifact manifests for both video and cortical output report `COMMITTED`, matching source SHA and file sizes.

This snapshot predates the final source-label fix described below and any subsequent image work. The parent task should publish a final snapshot after completing that work.

## Remaining execution limit

At verification time, this video run is `READY_FOR_REVIEW`: TypeSafe returned KEEP at 0.27 confidence and the unchanged 0.70 floor caused ASK_HUMAN. Generation, evaluation, research, summary, and sponsor delivery are verified. Automatic child generation is not verified, and the readiness table correctly retains `full_loop_verified: false`. The image run and the overall automatic revision loop remain work in progress. An online notebook worker is not proof of guaranteed 24/7 hosting.

## Corrected telemetry label

`diagnostic_telemetry.py` previously labeled every NotebookEvidence entry `standalone_notebook`, including this campaign's summary. It now preserves the persisted `source_kind`. Eight focused telemetry tests passed. No gate thresholds, evaluator results, or readiness criteria were changed.

Machine-readable records are in `artifacts/verification/meowstore-research-run.json`, `meowstore-cortical-integrity.json`, `meowstore-weave-readback.json`, and `meowstore-wandb-artifact-readback.json`.
