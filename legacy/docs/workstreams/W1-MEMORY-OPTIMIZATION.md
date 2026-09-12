# Workstream 1 — memory optimization patch

Date: 2026-09-11

Scope: model-free lifecycle hardening for the real TRIBE + optional TSAM + Kragel + ensemble path on a 24 GiB Apple-MPS host. No model weights were imported, no service was started or stopped, and no inference was run for this patch.

## Changes

- `scripts/windows_job.py` now terminates an isolated POSIX process group, with a bounded TERM→KILL escalation. Windows retains the existing job-object ownership behavior.
- `backend/neuroloop/worker.py` starts each run in a new POSIX session and uses group cleanup on cancellation, timeout, pressure, or supervisor exit. Direct `--run-id` entry also honors the execution hold.
- `backend/neuroloop/execution_guard.py` clamps `NEUROLOOP_MPS_MEMORY_RESERVE_GIB` to a hard minimum of 1.5 GiB. Invalid values still fail closed to the conservative 3 GiB reserve.
- `backend/neuroloop/inference.py` wraps TRIBE prediction in `torch.inference_mode()`, drops the stage-local TRIBE reference before TSAM/Kragel, runs garbage collection, and asks the MPS allocator to release unused cached blocks when available.
- `backend/neuroloop/tsam.py` releases its CPU model and removes its exact per-evaluation `tsam/` working directory in a `finally` block. `scripts/evaluation_entry.py` removes evaluator-owned audio/presentation intermediates even when evaluation raises.
- Worker reference arrays are copied once from short-lived mmaps and the mmap is closed immediately. API/comparison paths now close request-scoped mmaps explicitly.
- `scripts/verify_real_tribe.py` now checks the execution hold before importing model/runtime modules.

## Cache policy

No model weights, project caches, user files, or macOS-wide caches were deleted. The versioned `cache/tribe-local-q4-int8-*` directory is a project-owned feature cache, but deleting it would increase future cold-start work and is not proven to reduce active unified-memory pressure. The safe cleanup target added here is limited to evaluator-owned temporary media under an individual result directory.

## Model-free verification

The focused tests cover the hard MPS reserve floor, held direct worker entry, POSIX descendant cleanup, and mmap closure. Syntax/bytecode checks should also be run. These checks prove lifecycle behavior only; they do not establish the peak memory of TRIBE, TSAM, MPS allocator behavior, or whether the complete loop fits on this Mac.

## Remaining blockers

The prior real-run evidence showed available RAM dropping below the 1.5 GiB reserve before complete secondary-stage evidence. The patch can prevent orphaned descendants and reduce retention between stages, but only a separately approved, guarded real-model measurement can quantify the resulting peak. If that measurement still breaches the reserve, the workload needs a smaller model/input, CPU/off-host execution, or staged execution across separate processes; optimization alone cannot be promised to make the full loop fit.
