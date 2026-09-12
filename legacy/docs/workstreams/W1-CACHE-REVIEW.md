# W1 cache review — macOS

Date: 2026-09-11
Scope: project-owned and user-level cache behavior relevant to NeuroLoop on
Apple Silicon.  This review is read-only.

## Verdict

No cache, model weight, user file, macOS-wide cache, database, service, or
quarantine state was deleted or changed.  The new
[`scripts/audit_project_caches.py`](../../scripts/audit_project_caches.py) emits
an inventory and a manual-review allowlist.  It has no cleanup mode that can
delete files; `--dry-run` only labels the same advisory output.

The largest observed disk cache is the user-level uv cache at
`/Users/adityadas/.cache/uv` (2,595,653,598 bytes, 2.42 GiB).  The project
TRIBE feature cache is 3,655,145 bytes (3.49 MiB).  Neither number is a live
MPS allocation.  The earlier guarded run recorded only 616,972,288 bytes
(about 0.57 GiB) of available host memory against the 1.5 GiB execution
reserve; clearing a few megabytes of feature files cannot be treated as a fix
for that unified-memory peak.

## Checkout and merge state

The audit began after checking the branch and refreshing the remote.  The
remote fetch was attempted but GitHub authentication was unavailable in this
environment (`fatal: could not read Username for 'https://github.com'`).  The
checkout already had a clean merge commit, `23bf6af`, containing the locally
known `origin/main` at `7d063e7`; no second merge was possible without remote
credentials.  Unrelated in-progress agent changes were left untouched and
unstaged.

This limitation means the report is based on the repository contents and the
local runtime snapshot available on the Mac, not an independently fetched
remote tip.

## What was inspected

The source paths and policies were traced through:

- [`.gitignore`](../../.gitignore), which ignores `cache/`, model downloads,
  `.runtimes/`, and runtime `data/` while retaining static geometry.
- [`models/load_local_tribe.py`](../../models/load_local_tribe.py), which sends
  TRIBE feature intermediates to a versioned `cache/tribe-local-*` directory.
- [`tribev2-balanced-qv-local/load_quantized_tribev2.py`](../../tribev2-balanced-qv-local/load_quantized_tribev2.py),
  which uses a loader cache and writes chunk intermediates below
  `cache-int8/chunks`.
- [`backend/neuroloop/inference.py`](../../backend/neuroloop/inference.py),
  which writes result evidence and audio intermediates under `data/results`.
- [`scripts/evaluation_entry.py`](../../scripts/evaluation_entry.py), which
  attempts to remove evaluator-owned audio/presentation files and the TSAM
  scratch directory in its `finally` block after an evaluation ends.
- [`backend/tests/conftest.py`](../../backend/tests/conftest.py), which creates
  test scratch directories under `data/tmp`.

The runtime sizes below were measured against the active local checkout at
`/Users/adityadas/Desktop/Programming/Hackathons/NeuroLoop`.  The audit tool
does not import NeuroLoop, load model code, start services, or read model
weights into memory.

## Inventory: disk paths versus live RAM

| Ownership | Classification | Path | Observed size | Policy | Live RAM? |
|---|---|---|---:|---|---|
| Project | Feature disk cache | `cache/` (`tribe-local-q4-int8-d15105071677`) | 3.49 MiB; 18 files, 7 directories | Manual review only; preserve by default | No |
| Project | TRIBE loader disk cache | `tribev2-balanced-qv-local/cache-int8/` | 0 B in this snapshot | Preserve by default | No |
| Project | Test scratch | `data/tmp/` | 21.62 MiB; 766 files, 166 directories | Narrow manual review of `neuroloop-tests-*` only | No |
| Project | Derived media | `data/renders/` | 214.55 KiB | Preserve unless unreferenced | No |
| Project | Runtime results | `data/results/` | 2.14 MiB | Preserve; includes evidence and failure receipts | No |
| Project | Uploaded/source media | `data/assets/` | 290.06 KiB | Never auto-clean | No |
| Project | Logs | `data/logs/` | 29.95 KiB | Preserve for recovery/debugging | No |
| Project | Database | `data/neuroloop.db` | 4.00 KiB | Never auto-clean | No |
| Project | Execution hold | `data/inference-quarantine.json` | 664 B | Never modify in this audit | No |
| Project | Model weights | `models/` | 6.2 GB by separate read-only `du` check | Never delete | No; disk-backed weights |
| Project | TRIBE weights/runtime | `tribev2-balanced-qv-local/` | 1.6 GB by separate read-only `du` check | Never delete | No; disk-backed weights |
| Project | Runtime environments | `.runtimes/` | Presence-only in the tool | Preserve | No; installed files |
| User | uv download/build/index cache | `/Users/adityadas/.cache/uv` | 2,595,653,598 B (2.42 GiB) | Package-scoped manual review only | No |

The `data/` entries are runtime state or media, not interchangeable caches.
Their disk size does not predict the peak memory of a future model process.

The live-memory side of the audit is separate:

- `sysctl -n hw.memsize` reported `25,769,803,776` bytes (24 GiB).
- The dependency-free tool reports host total memory and its own small peak RSS
  when available; it intentionally does not claim an MPS allocation number.
- A read-only `vm_stat` sample showed active, inactive, wired, compressed,
  purgeable, and file-backed page classes.  Those page classes are host memory
  accounting, not the byte size of a project cache.
- The guarded execution record remains the relevant failure evidence: available
  memory fell to `616,972,288` bytes, below the 1.5 GiB reserve, before complete
  secondary-stage evidence.  This review did not clear or edit that hold.

## Dry-run allowlist

The tool emits each item with `automatic_action: "none"`, an exact path scope,
and preconditions.  The current Mac snapshot produced 21 advisory records:

1. Seventeen `data/tmp/neuroloop-tests-*` directories totaling 22,673,375
   bytes (21.62 MiB).  These are the narrowest project-owned candidates, but
   they must not be touched while tests or failure investigations reference
   them.
2. Two leftover `audio-16k.wav` files under incomplete result directories
   (160,574 bytes each) and one incomplete-result `tsam/` directory (1,242,346
   bytes).  They are evaluator-owned intermediates only after confirming the
   result is failed/incomplete, no evaluator process is active, and the parent
   receipt/prediction files are retained.
3. The uv cache is represented as one conditional package-scope review record.
   The whole `/Users/adityadas/.cache/uv` directory is not an allowlisted delete
   target.  A package/cache key must be chosen manually, and the locked
   environments must remain reproducible.

The `cache/tribe-local-*` directory is deliberately placed in
`excluded_from_cleanup`, not in the RAM-cleanup allowlist.  Removing it would
discard reusable features and force recomputation; it is not evidence of a
resident MPS tensor.

## Known uv cleanup result

The durable local observation is:

```text
uv 0.12.10 (Homebrew 2026-09-04 aarch64-apple-darwin)
uv cache dir -> /Users/adityadas/.cache/uv
current cache size -> 2,595,653,598 bytes (2.42 GiB)
```

The current `uv cache clean --help` output accepts optional package arguments,
but exposes no `--dry-run` option.  This audit did not invoke `uv cache clean`
or any equivalent removal command, so its report field is
`cleanup_result: "not_run"`.  No durable prior cleanup receipt was found in
the repository or the local shell-history files checked.  Therefore the report
does not claim that a previous cleanup freed any particular amount of disk or
RAM.

The cache contains uv's simple-index metadata, wheels, sdists, archives,
interpreter records, and environment records.  It can be useful for rebuilding
the pinned environments.  Broad cleaning would trade disk space for later
network downloads and should not be used as a proxy for MPS memory management.

## Why feature-cache deletion does not prove lower MPS peak RAM

NeuroLoop's feature cache is serialized disk output from preprocessing.  During
a cold or uncached evaluation, the process still has to load the frozen model,
decode the media, create input tensors, run the video/audio/text encoders, and
materialize model outputs.  The quantized video loader also converts hidden
states to CPU `float32` arrays while the result tuple is being assembled.  On
Apple Silicon, CPU and MPS allocations draw from the same unified physical
memory pool.  The peak is therefore driven by the live process's overlapping
weights, temporary tensors, hidden states, decoded frames/audio, Python object
graphs, and allocator bookkeeping—not by the number of serialized feature files
on disk.

Deleting a feature cache can have the opposite operational effect: it forces
re-encoding and increases cold-start work.  It might lower a later disk-cache
hit's I/O footprint, but it cannot release allocations held by an already
running process and cannot establish a lower MPS peak.  Only a guarded,
instrumented model measurement can answer that question.

## Read-only proof and tests

Commands run after adding the tool:

```text
$ python3 -B scripts/audit_project_caches.py --self-test
{"contract": "read-only inventory and advisory allowlist", "passed": true}

$ python3 -B -c 'from pathlib import Path; compile(Path("scripts/audit_project_caches.py").read_text(encoding="utf-8"), "scripts/audit_project_caches.py", "exec"); print("syntax_ok")'
syntax_ok

$ python3 -B scripts/audit_project_caches.py \
    --root /Users/adityadas/Desktop/Programming/Hackathons/NeuroLoop \
    --dry-run --json | jq '.read_only'
{
  "allowlist_is_advisory": true,
  "deletions_performed": [],
  "mode": "report_and_dry_run",
  "models_started": [],
  "processes_started": [],
  "quarantine_changed": false,
  "renames_performed": [],
  "services_changed": [],
  "writes_performed": []
}
```

The tool's AST self-test rejects filesystem mutation calls and imports of
model/data-runtime modules.  The implementation uses only standard-library
path/stat/scan operations plus optional `psutil.virtual_memory()` telemetry;
there is no output-file option, subprocess call, model import, service call,
quarantine write, or delete API.

`git diff --check -- scripts/audit_project_caches.py docs/workstreams/W1-CACHE-REVIEW.md`
also passed.  The command-line audit was run against both this worktree and the
active local checkout; it left the authorized report/tool paths unchanged after
each read-only run.  Other agent modifications already present in the worktree
were not staged or included.

## Retention decisions

### Narrow candidates for a future, separately approved manual cleanup

- Completed, unreferenced `data/tmp/neuroloop-tests-*` scratch directories,
  one exact directory at a time.
- Exact evaluator-owned `audio-16k.wav`, `presentation.mp4`, or incomplete
  `tsam/` intermediates in a failed result directory after process quiescence
  and receipt review.
- One explicitly selected uv package/cache entry after confirming the locked
  environments and network source are available.

### Explicitly excluded

- `cache/tribe-local-*` and `tribev2-balanced-qv-local/cache-int8/` as a
  supposed RAM remedy.
- Model weights, `.runtimes/`, `data/assets/`, `data/results/`, `data/exports/`,
  `data/logs/`, the SQLite database, and `data/inference-quarantine.json`.
- Generic `/Users/adityadas/Library/Caches` or any macOS-wide cache.  No broad
  system-cache inspection or cleanup was attempted.

## Limitations

- GitHub fetch could not authenticate, so the latest remote tip could not be
  independently refreshed in this environment.
- `psutil` is unavailable to the dependency-free audit process on this host;
  the tool reports total memory but leaves current available bytes and native
  MPS allocator counters unknown.  `vm_stat` and the prior guard receipt are
  contextual evidence, not a substitute for a guarded model profiler.
- The report does not determine whether a particular uv artifact is referenced
  by an active installer or environment; package-level cleanup remains a
  human-reviewed operation.
- Directory scans do not follow symlinked directories and are capped by
  `--max-entries`; protected model/runtime folders are presence-only by design.
- No model or service was run for this audit, so it cannot establish that the
  complete TRIBE/TSAM/Kragel path fits in 24 GiB.  It only documents which disk
  paths are and are not plausible cleanup targets.
