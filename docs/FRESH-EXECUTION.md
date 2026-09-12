# Fresh execution and UI verification — September 11, 2026

This report supersedes the earlier refresh's statement that no fresh model inference ran. Verification uses the isolated Windows model runtime, CPU only, with CUDA hidden before importing PyTorch. The existing graphics-crash hold remains unchanged; these results do not establish GPU stability.

## Implemented and checked

- Restored the earlier Brain Lab layout: large cortical panel and timeline beside the source player and provenance. Audio and video share the recorded stimulus-time selection. Runtime is a separate measurement.
- Rebuilt the landing composition with oversized editorial typography, a graphite anatomical plate, ruled process sections and a compact footer. Preserved the logo and meme.
- Replaced the blue-grey dark theme with graphite surfaces, near-white text and restrained sage accents. Verified in actual Edge with fresh saved output.
- Repaired a merged inference block that referenced undefined `tribe_profile` and deleted objects before the following evidence block used them. The first failed attempt remains recorded; the successful retry is a separate run.
- A fresh motion run exposed a second merge regression: video compaction produced 1,408 features for a checkpoint expecting 2,816. The corrected implementation preserves all 20 selected layer summaries and both downstream group means, pooling only tokens before host transfer. A model-runtime test compares it numerically with the actual Neuralset aggregation implementation.
- Replaced Exca's POSIX process-liveness probe on Windows with read-only `psutil.pid_exists`; an interrupted worker was then reclaimed successfully. This repairs cache recovery, not the graphics driver.
- Static image presentations now use lossless intra frames. All 60 frames in the five-second round-trip check had the same decoded hash. Exact identical-frame feature reuse retains an actual model forward result; moving or changed frames cannot use it.
- Added missing matching `torchaudio` and `timm` dependencies to the isolated Windows runtime and regenerated its pinned lock. Dependency checks pass.
- Added a process-scoped CPU verification entrypoint. It keeps the GPU lock, bounded worker, immutable project snapshot, memory reserve, artifact validation and MCP queue contract. It does not enable the general worker or Launch agent.
- Kragel now requires an explicit reviewed registration and transfer-validation receipt before contributing to decision scores. Unvalidated scores remain diagnostic only. Missing historical eligibility flags do not qualify as validation.

## Fresh results

| Input | Fresh saved output | Inference time | Evaluation |
|---|---|---|---|
| Six-second real Apollo audio | 7 × 20,484 finite values | 12.922 s | `822a4fe1-6a8b-4988-afde-f523b5a8ddc4` |
| Explicitly timed text | 5 × 20,484 finite values | 17.265 s | `f065c8a3-9512-4e4e-8642-159aeacc1fea` |
| One-second real Apollo motion clip | 1 × 20,484 finite values | 246.031 s | `48a9b98a-a7ac-4a0c-941d-0195b3071fea` |
| Image presented for eight seconds | 8 × 20,484 finite values | 90.734 s | `68c3742b-b816-48ab-ba68-91020bdcae22` |

All ran on CPU, with actual artifact-manifest and array checks. The one-second motion clip has only one cortical timestamp; it does not demonstrate a longer motion timeline. The six-second visual run exceeded the CPU budget. These are technical checks on selected inputs, not throughput or stability benchmarks. Profiles changed as bugs were fixed; the application correctly prevents comparing different profiles as if they were identical.

Feature caches now use the full checked model/processor/code profile plus resolved device. This prevents CPU/GPU and changed-weight reuse even though Neuralset excludes device from its own extractor identifier. Historical caches remain on disk but are not reused by the corrected namespace.

Audio: actual six-second NASA Apollo audio, TRIBE + Wav2Vec-BERT on CPU. Run `364f75f7-547b-419e-8f1e-131b5a1d6a5f`; evaluation `822a4fe1-6a8b-4988-afde-f523b5a8ddc4`. Output is **7 × 20,484 finite values**; measured inference time **12.922 seconds**. The manifest and prediction hash were checked. Edge displayed the actual response, source audio, timestamps, hemisphere controls and magnitude palette.

Text: explicitly timed words, local NF4 Llama-3.2-3B + TRIBE, **5 × 20,484 finite values**, **17.265 seconds**. Run `c715f83c-2d9d-4d44-9027-629e7a6a16ad`; evaluation `f065c8a3-9512-4e4e-8642-159aeacc1fea`. Timings are a designed presentation, not measured reading speed. The real authenticated HTTP export returned a valid ZIP containing the source text, evidence and finite prediction array; see `artifacts/fresh-model-verification/export-check.json`.

TSAM: actual six-second audiovisual Apollo clip, fresh strict loading and CPU forward pass, **4.422 seconds**, one complete five-second window and eight finite logits. See `artifacts/fresh-model-verification/tsam-cpu-result.json`. This is an out-of-domain technical test without human emotion labels; its highest logit is not evidence of a viewer's emotion.

Combined branch check: run `c435e4b5-1154-40b7-9e56-f337ce3f3cf0`, evaluation `f97ea87b-c878-4f40-b6f6-54a47977f9c9`, **6 × 20,484 values in 113.422 seconds**. The five-second input combines a constant TIDELINE visual with real Apollo audio solely to check wiring; it is not a natural advertisement or validation sample. TRIBE, TSAM and Kragel all completed. TSAM returned eight logits; Kragel returned seven diagnostic trajectories. Kragel reports `registration_verified=false`, `decision_eligible=false`, and excludes padded row 5. The ensemble explicitly excludes Kragel with the reason `Registration and TRIBE transfer validation required`. Browser inspection confirmed the actual logits, diagnostic trajectories and provenance are rendered.

The first combined run completed TRIBE/TSAM but Kragel failed its source-duration check. The next exposed a zero-overlap padded terminal interval. Both remain recorded. The verifier now checks each requested readout's status before reporting an all-branches pass; the final receipt passes this stricter check. Original cortical predictions remain intact; diagnostic scoring only uses the portion of each interval inside the actual media duration.

[Final combined Weave trace](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/57ed459d-51c8-49e7-808e-06a6b9a8ef0e). Full local numerical evidence: `artifacts/fresh-model-verification/combined-evidence-final.json`.

The final trace was independently read back through official W&B MCP; `weave-final-readback.json` preserves the matching IDs/profile/timing and null exception. The authenticated application export produced `artifacts/fresh-model-verification/combined-evidence.zip` (8,346,219 bytes). Its ZIP integrity, included finite prediction array, successful readout statuses and Kragel decision exclusion were verified in `combined-export-check.json`.

Per-run machine-readable receipts are saved under `artifacts/refresh-verification/cpu-run-*.json`. Failed attempts remain failures and are not counted as successful inference.

## Repeating a bounded CPU check

Keep the normal application running. Choose a managed project ID from MCP or the workspace, then run from the project root:

```powershell
.runtimes/model/Scripts/python.exe scripts/verify_cpu_run.py --project-id <project-id> --max-seconds 600 --cpu-threads 6
```

The verifier claims only its newly queued run, never the general queue. It hides CUDA before model imports, preserves the original graphics hold, reserves 4 GiB free RAM, caps threads and duration, and refuses to count an existing cached evaluation as a fresh pass. Optional `--include-tsam` requires adequate audiovisual duration; `--include-kragel` adds unvalidated diagnostics, not scientific eligibility. Inspect the receipt if interrupted; do not interpret a nonzero exit as a completed result.

## Actual sponsor and MCP evidence

- [Molab evidence notebook](https://molab.marimo.io/notebooks/nb_B79BrKA5Rh4UNJxj9NQ1kf): saved and executed in the user's account. Eleven chart views using sanitized historical numerical records and the fresh TSAM result. Parallel coordinates and TSAM plots were browser-verified. No credentials, raw media or database uploaded. See [Molab details](MOLAB.md).
- [Fresh audio Weave trace](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/562f0b92-9d69-46cd-bf32-8d4306ac05cf): independently retrieved through the official W&B MCP. Run ID, evaluation ID, profile, timestamps and compute seconds match local evidence; no remote exception was reported.
- Fresh stdio NeuroLoop MCP queued the run through `evaluate_creative`; the current conversation's MCP `get_evidence` retrieved its actual numerical output. This is more than configuration or tool discovery.
- Local marimo at port 2718 reads the live local ledger. Molab is a separate hosted snapshot; it does not automatically follow local database changes.

## Checks and remaining gates

Backend suite: **215 passed, 5 skipped, 2 dependency deprecation warnings**. Two of those skips require the isolated model runtime; both passed separately there, including the 2,816-feature numerical equivalence test. Frontend production build passed. Browser checks covered the new landing, restored Brain Lab, fresh image/audio/combined evidence, dark appearance, open hemispheres, final stimulus-time selection, actual TSAM/Kragel readouts, a real HTTP MCP handshake with 21 tools, local marimo HTTP 200 and authenticated Weave connectivity.

The repeated Windows 0x113 cause is still unknown. Protected dumps could not be read and a debugger is not installed; see [crash diagnosis](CRASH-DIAGNOSIS-CURRENT.md). CPU success does not prove a repaired graphics driver.

TSAM class mapping, held-out reproduction, leakage review and intended-domain calibration remain open. Kragel needs a complete, provenance-bound surface-RAS-to-MNI transform and held-out TRIBE transfer evaluation; the MNI305-to-MNI152 transform alone is insufficient. See [registration requirements](KRAGEL-REGISTRATION.md).

ARIA has an actual prior review, but the full Launch experiment is still unaccepted after the crash. W&B Inference, TypeSafe and CoreWeave compute/storage remain deferred. Scientific validation, commercial permissions and original-versus-quantized accuracy cannot be replaced by successful execution tests.

The installed Launch SDK's `pop_from_run_queue(queue_name, entity, project, agent_id)` claims the next job before returning its specification; it has no atomic claim-by-item-ID argument. A one-proposal acceptance runner must use a dedicated queue with exclusive submission control or a provider-supported targeted claim. Starting the shared queue agent with a general CPU worker could claim unrelated work, so it was not done. `max_jobs=1` limits concurrency rather than total jobs. The existing entrypoint also queues local work and waits; it does not itself execute a targeted CPU worker.
