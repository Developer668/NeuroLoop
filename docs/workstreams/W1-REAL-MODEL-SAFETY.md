# Workstream 1 — real-model safety and loop gate

Date: 2026-09-11
Scope: protected-baseline verification, real-model/MPS memory investigation, and a bounded end-to-end handoff. No model was run by this workstream.

## Verdict

**BLOCKED for fresh real-model end-to-end acceptance.** The existing Apple MPS quarantine is active because host available memory fell to 299,040,768 bytes (about 0.28 GiB), below the hard 1.5 GiB reserve. The only five-second audiovisual attempt reached and saved TRIBE prediction data, then failed before TSAM/Kragel/ensemble completion. Existing one-second MPS TRIBE output is not a complete loop and does not clear the hold.

This is an investigation-complete verdict, not a release claim. The hold, weights, caches, database, services, and historical receipts were not changed.

## Baseline and checkpoint integrity

The isolated worktree was checked at:

```text
HEAD:                              f5e1132c5513319d41a15a40c461b9b73210f60b
checkpoint/pre-orchestration-20260911: f5e1132c5513319d41a15a40c461b9b73210f60b
working tree:                      clean before this report
```

The protected checkpoint tree and `HEAD` had no diff, `git diff --check` was clean, and the checkpoint was reachable by both its branch ref and the worktree `HEAD`. The integration branch was inspected only as a separate ref; it was not merged, reset, or modified. Large model/runtime/data receipts are intentionally outside the protected Git snapshot.

The original checkout was inspected read-only. Its active state is:

```text
data/inference-quarantine.json: active=true
reason: Available system memory fell below the 1.5 GiB execution reserve
created_at: 2026-09-11T09:42:24.785813+00:00
interrupted_run_id: 22594d8a-e2e2-4fdb-bde7-62095880ec63
ram_total_bytes: 25769803776
ram_available_bytes: 299040768
accelerator: mps
```

The original checkout currently reports loopback services on 8010 (API), 3010 (web), and 2718 (research). `data/services.json` still lists a worker because that service was started before the hold was written; the worker process is idle and the hold makes it wait. No worker restart, stop, queue submission, quarantine edit, or model command was performed.

## Existing evidence, classified honestly

Evidence inspected in the original checkout:

| Receipt or observation | What it proves | What it does not prove |
|---|---|---|
| `docs/AUDIT.md` and `docs/CRASH-RECOVERY.md` | Prior recovery audit, repeated Windows `VIDEO_DXGKRNL_FATAL_ERROR (0x113)`, saved-array/media integrity, and the execution hold | A diagnosis or cure of the Windows graphics fault |
| `data/results/mac-mps-smoke/evidence.json` | A real one-second video-only TRIBE result on MPS: 1 × 20,484, 105.146 s, finite output, 12.7 GB available at preflight | Five/ten-second audiovisual work, TSAM, Kragel, ensemble, local edit, or repeat stability |
| `data/results/1c6618.../evidence.json` | A separate real one-second video-only MPS TRIBE result: 1 × 20,484, 97.794 s, 12.85 GB available at preflight | Any complete response-target loop |
| `data/results/485470.../process.log` and `prediction.npy` | The five-second audiovisual attempt decoded audio, encoded TRIBE video features, and saved a prediction array before termination | A valid `evidence.json`, TSAM logits, Kragel trajectories, ensemble, edit, or repeat |
| `data/results/485470.../process-error.json` | The child ended with `BrokenPipeError` while reporting the TSAM stage after the supervisor stopped the run | A model failure root cause; the broken pipe is downstream of termination |
| `data/inference-quarantine.json` and SQLite run row | The guard stopped run `22594d8a...` when available RAM was below 1.5 GiB; database integrity was `ok` and the run is failed with one evaluation reserved | A safe basis for retrying while the hold remains active |
| `data/logs/*.log` and `data/services.json` | API/web/research were serving; the current service manifest is loopback-only; worker startup messages exist | That the full model worker is currently healthy or that the research log is clean (the log contains historical dependency errors) |

The historical `docs/VALIDATION.md` and `docs/MODEL-COMPATIBILITY.md` describe earlier real NASA and controlled-edit work, including approximately 2.81 GiB peak PyTorch allocation on CUDA. They explicitly label it historical and state that no execution occurred after recovery. It is not fresh evidence for this hold and is not counted as completion here. No mocked evaluator output was used.

## Process and memory lifecycle findings

### Process graph

The current path is serialized but nested:

```text
manage.py supervisor
├── API (app runtime)
├── worker (model runtime; one data/gpu-worker.lock)
│   └── run_worker.py --run-id (one run supervisor child)
│       └── evaluation_entry.py (one child per evaluation; loads TRIBE)
│           └── ffmpeg subprocesses during decode/render
├── web
└── marimo research
```

`worker.supervise_run` starts one run child and polls it. `worker.evaluation` then calls `inference.evaluate`, which starts a fresh `evaluation_entry.py` process for each uncached evaluation. This per-evaluation boundary is the main fix for the previously observed retained model memory: after the child exits, the OS can reclaim TRIBE and encoder allocations before a candidate evaluation. The run parent itself remains resident, but it imports no model weights.

### TRIBE peak mechanisms

- `models/load_local_tribe.py` validates local shards, constructs the official TRIBE model, uses the local INT8 V-JEPA video loader, keeps audio on CPU, and configures a shared 2 Hz grid. The loader's cache directory is versioned from `infrastructure/runtime/model.lock`.
- `load_quantized_tribev2.py` constructs the video model on `meta`, loads SafeTensors, moves it to the requested device, and requests `output_hidden_states=True`.
- The local video wrapper then converts every returned hidden-state tensor to CPU FP32 (`tuple(x.to(device='cpu', dtype=torch.float32) ...)`). The temporary device tensors and the new CPU copies coexist while the tuple is built. This is a real peak candidate even though it reduces resident device memory afterward.
- The application sets `torch.cuda.set_per_process_memory_fraction(0.75)` only for CUDA and records `torch.cuda.max_memory_allocated()`. It does not expose a native MPS allocation counter; MPS is unified memory, so host available RAM and process RSS are the only current external proxies.
- The application does not call `torch.cuda.empty_cache`, `torch.mps.empty_cache`, or an explicit `del`/`gc.collect` sequence after the full TRIBE/TSAM path. Process exit is the intended reclamation boundary. That is acceptable for serial child isolation but leaves the in-process peak exposed until the evaluation completes.

### TSAM, Kragel, and ensemble overlap

`inference._evaluate_in_process` currently executes the secondary stages in this order:

```text
TRIBE prediction → TSAM (CPU, when requested) → Kragel (NumPy, when requested) → ensemble
```

The requested handoff names Kragel before TSAM; the implementation order is the reverse. Both stages are covered by the procedure below, but a strict Kragel-before-TSAM release contract would require an explicitly reviewed core-ordering change outside this workstream.

During the same evaluation child, the TRIBE model remains referenced while `predict_video` loads the strict eight-class TSAM ResNet50, extracts 10 FPS JPEGs, decodes WAV audio, forms three mel channels, and evaluates full five-second windows. The TRIBE prediction remains live for subsequent Kragel decoding. TSAM's local model and imported runtime state are not explicitly released; normal Python teardown and child exit are the reclamation mechanism. Kragel's cached seven normalized 20,484-value patterns are small compared with encoders, but its decode creates centered/normalized response copies. The ensemble is numerically small and not the source of the observed host-memory collapse.

### Repeat/edit lifecycle

- `worker.execute_run` holds references to memory-mapped saved predictions for references and the current best candidate. These arrays are about 1 MB per 11 × 20,484 FP32 prediction and are not the main peak, but mappings/file descriptors persist through the run.
- The controlled edit renders a local FFmpeg candidate, then starts another fresh evaluation child. The candidate's model memory is therefore not intended to overlap with the baseline's model child after normal exit.
- On Windows, the outer job object owns the run child and inherited descendants. On POSIX/MPS, `OwnedJob` is a no-op and `worker.supervise_run` terminates only the direct run child. If that child is killed while an evaluation grandchild is live, the grandchild may outlive the run parent because no process group/session is created. This is a concrete MPS/RAM leak risk on cancellation, pressure, timeout, or host shutdown and needs a separately approved core-worker fix.
- The same direct-child limitation exists in `scripts/manage.py` for service descendants on POSIX. It is not evidence that an orphan exists now; it is a lifecycle hazard to check in a future bounded run.

### Guard and bypass findings

- `execution_guard.pressure_reason` fails closed at 1.5 GiB only when the Apple override is active; otherwise its default reserve is 3 GiB. The Mac startup script sets `NEUROLOOP_ALLOW_MPS_INFERENCE=true` and `NEUROLOOP_MPS_MEMORY_RESERVE_GIB=1.5` by default.
- The guard's `max(1.0, configured)` permits a caller to lower the MPS reserve below 1.5 GiB. This workstream did not change it because the scope excludes core worker/guard behavior; the integration owner must close that policy gap before any release test.
- `scripts/verify_real_tribe.py` calls the loader directly and does not consult the execution guard. `scripts/run_worker.py --run-id` calls `worker.process` directly without an in-function guard. These are unsafe direct-entry paths while quarantined and must not be used for this gate. `verify_real_media.py` goes through the held service and is rejected by the domain guard.

## Bounded 5-second → 10-second measurement procedure

This is a future handoff procedure only. Do not execute it until the blocker below is cleared and a human explicitly approves the test. The new `scripts/profile_real_loop.py` is read-only: it monitors an already-running supervisor and does not launch a command or import a model.

### Preconditions and evidence bundle

1. Preserve the database, model weights, caches, current quarantine JSON, and all prior receipts. Verify the checkout/ref hash above and run the model-free tests first.
2. On Windows, an administrator copies the latest minidump identified in `docs/CRASH-RECOVERY.md` into a private local diagnostics directory and records WinDbg `!analyze -v`, failure bucket, implicated module/stack, driver, firmware, and hardware findings. A temperature correlation alone is not sufficient.
3. For an Apple MPS test, the owner explicitly approves a one-run MPS exception while preserving the quarantine record. Do not delete, rewrite, or silently override the hold. Do not set `NEUROLOOP_MPS_MEMORY_RESERVE_GIB` below **1.5**.
4. Record hardware before the run: total RAM, available RAM, macOS/PyTorch/model-runtime versions, MPS device, and all other high-memory workloads. The hard acceptance floor is `ram_available_bytes >= 1.5 * 1024**3` at preflight and every profiler sample. A safer start target is at least 4.5 GiB available, derived from the historical ~2.81 GiB CUDA PyTorch allocation plus the 1.5 GiB reserve; that target is a recommendation, not MPS evidence.
5. For CUDA only, also require the existing preflight conditions: free VRAM ≥4 GiB and temperature <82°C. For MPS, there is no separate VRAM/free counter in the current application; capture unified host-memory evidence and mark native MPS allocated/reserved bytes as unavailable unless an approved in-process trace is added.

### Prepare two real audiovisual clips

Use the same real source with audio, trimmed to exactly 5.0 seconds and exactly 10.0 seconds. Keep source URL/license/hash and the trim command in the evidence bundle. Do not use `technical-motion-fixture.mp4`, mocked arrays, an old saved prediction, or a cached evaluation as the acceptance input. Upload each clip as a distinct managed asset and confirm its recorded duration and `has_audio=true`.

### Run the 5-second loop

1. Start the model-free profiler against the approved supervisor PID (or `data/services.json`):

   ```text
   <approved-app-python> scripts/profile_real_loop.py \
     --state-file data/services.json \
     --label real-loop-5s \
     --duration 300 \
     --interval 1 \
     --output data/verification/release/real-loop-5s-profile.json
   ```

   The 300-second wall bound is for observation; the run itself must use `max_seconds=240` or a separately approved bound. The profiler's output must show `models_imported=false`, `processes_started=false`, and `quarantine_changed=false`.
2. Queue one `mode=optimize`, `objective=response_target` run through the authenticated API or MCP. Use `max_evaluations=2`, `max_seconds=240`, exactly one permitted local operator such as `brightness_up`, both `include_kragel=true` and `include_tsam=true`, `tsam_research_acknowledged=true`, and a declared target. Do not use Launch for the first MPS measurement.
3. Confirm the run events/evidence show the complete baseline sequence: TRIBE prediction with a finite `N × 20,484` response, TSAM status `experimental` with one complete `[0,5]` window and eight finite logits, Kragel status `experimental` with seven finite trajectories, and `response_ensemble.profile=tsam55-kragel45-relative-evidence-v1`. Record stage timestamps from run events and align them to profiler samples.
4. Confirm the local edit rendered successfully, preserved duration/audio constraints, and a second evaluation child completed the same TRIBE → TSAM → Kragel → ensemble sequence. Record baseline/candidate evaluation IDs, both profiles, candidate decision, process-tree PIDs, per-sample RSS, minimum available RAM, and any CUDA counters. Do not call the result a human response or emotion probability.
5. Stop observation after the run reaches a terminal state or 300 seconds, whichever comes first. If the hard reserve is crossed, a process exits unexpectedly, or the host shows pressure, preserve the partial evidence and leave the quarantine active.

### Run the 10-second loop

Repeat the same procedure with the 10.0-second real audiovisual clip and a fresh cache key/output directory. Use the same two-evaluation budget and 240-second run bound. The TSAM receipt must contain two complete windows `[0,5]` and `[5,10]`; `omitted_tail_seconds` must be zero. TRIBE must save a finite response with the expected 20,484-vertex width. The edit/repeat and resource criteria are identical. Do not reuse the 5-second output as a cache hit.

### Acceptance record

The real-loop gate is not passed unless both clips have fresh, complete, non-mocked receipts with:

- terminal run status `completed`;
- TRIBE, TSAM, Kragel, ensemble, local render, and repeat evaluation all present;
- no `process-error.json`, broken pipe, timeout, cancellation, or host crash;
- every profiler sample at or above the 1.5 GiB available-RAM floor;
- no unexplained child process left after the run, and no second model worker concurrently resident;
- profile/runtime/weight hashes recorded and consistent across baseline and candidate;
- an explicit statement that MPS native allocator bytes are unavailable if no in-process trace exists; and
- the quarantine reopened only by the owner after reviewing the diagnostic/hardware evidence and approving the bounded workload.

A single earlier success, a saved array, a mocked evaluator test, a completed TRIBE-only run, or a service health check cannot satisfy this gate.

## Blocker and required handoff

The active quarantine is the immediate blocker and must remain active. Exact approval needed before any fresh real-model call:

1. **Hardware/diagnostic owner:** complete the Windows dump/vendor diagnosis if Windows is the target, or explicitly designate Apple MPS as the target and record its total/available unified-memory evidence.
2. **Runtime owner:** verify the model runtime and local weight manifests without importing model code; close the below-1.5-GiB configuration loophole before test approval.
3. **Integration owner/user:** explicitly approve the two bounded runs and the exact clip/operator/budget above. Approval must not authorize clearing the quarantine, bypassing the 1.5 GiB floor, or restarting an unsafe workload.
4. **Execution owner:** run the profiler beside the approved service, preserve all partial receipts, and stop on any reserve breach or unexpected child. Re-quarantine after either run; do not infer stability from a pass.

Until those handoffs are complete, the exact truthful state is **BLOCKED**. No fresh complete TRIBE → Kragel → TSAM → ensemble → local edit → repeat evidence exists.
