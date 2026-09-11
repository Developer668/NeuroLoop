# System audit — September 10, 2026, after crash recovery

**Verdict: actual outputs and working local review/integration services are verified. GPU execution is paused; production and stability gates remain open.** The latest Windows crash occurred during the reference evaluation of a bounded Launch experiment. It invalidates any claim that the full current pipeline is stable on this laptop.

## Current evidence

| Check | Result and receipt |
|---|---|
| Backend regression suite | 109 passed; `data/verification/release/backend-post-crash.xml`; two dependency deprecation warnings |
| Independent app installation | 110 packages, isolated, dependency check passed; same suite exercised in app-rehearsal |
| Model installation | 192 packages; main and model-rehearsal dependency checks passed |
| Official W&B MCP runtime | 121 packages; dependency check passed |
| Frontend production build | Passed after the dedicated Neuro, footer and execution-hold changes |
| Recovery audit | All 16 checks passed; `data/verification/release/recovery-audit.json` |
| Saved predictions | 29 finite, nonconstant arrays; recomputed summaries matched; first API frame exactly matched each stored array |
| Media integrity | 32 managed asset SHA-256 values matched |
| Database | SQLite integrity OK; zero queued/running jobs |
| MCP | HTTP and stdio discover the same 18 tools; actual status/ledger/evaluation calls succeed; held execution is rejected |
| Auth | Missing auth rejected, foreign-origin session request rejected, server-side session revocation verified |
| Startup | Only API, web and marimo started; model worker and Launch agent omitted |
| Weave | Actual trace export and readback; durable receipts visible in Connections |
| W&B MCP | 19 read-only tools; actual project trace query returned HTTP 200 after recovery |
| ARIA | Reviewed actual run history and returned a constrained contrast-up proposal; response saved in `aria-review.txt` |
| Launch | Installed v1 job and local queue dispatched actual work; latest run **crashed**, reconciled locally/remotely as failed |
| Backup restore | Earlier 539-file backup restored twice; a fresh 560-file post-crash snapshot restored again with the execution hold preserved; checksums, database and media consistency passed |
| npm advisory scan | Zero reported known vulnerabilities in saved scan |
| App Python advisory scan | Zero reported known vulnerabilities in saved scan |
| Model Python advisory scan | Three raw matches, two unique advisory IDs; see scoped triage below |

## Neural output versus stability

The isolated runtime produced evaluation `cdfaacce-e365-4eca-8447-ba323c64d5e5` in run `3fa0e490-2acf-4159-a9e9-7ee2f545a9f6`: six frames × 20,484 vertices, 42.485 seconds. The retained `runtime-audit/runtime.json` records fresh composition, MCP inference, comparison and ZIP evidence. Model feature caches can be reused; the measurement does not prove cold-start performance.

After adding the required spaCy 3.8 language asset and updating model provenance, audiovisual run `5df6542e-b183-4a08-b05e-adcf81175aed` completed its baseline in 89.437 seconds. The next/reference evaluation was interrupted by `VIDEO_DXGKRNL_FATAL_ERROR (0x113)`, logged at 21:47:45 Pacific. Baseline output survived. The last saved monitor samples include GPU temperature reaching 90°C and available system RAM below 3 GiB. The dump is unreadable to this process; pressure is observed, causation is unproven.

[Actual failed W&B run](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/runs/n8jfg4uh). Remote state was read back as `crashed`; summary `local_status=failed` was confirmed. Receipt: `launch-0e2bcff4-94fe-4759-bf64-972e464bfb41.json`.

No neural execution was performed after recovery. New pressure guards were verified with owned sleeping processes and controlled telemetry, not by another GPU stress test. A clean second model installation passed actual MoviePy decode/resize/encode/redecode, but **full second-installation inference has not passed**.

## Dependency scope

All five new environments exclude system site-packages and pass dependency consistency checks. The model uses explicit TRIBE and MoviePy packaging forks; compatible resolver metadata is not proof of all upstream features or model accuracy.

- Accelerate 1.13.0: `PYSEC-2026-3804` / `CVE-2026-69112`, checkpoint-index path traversal; no fixed version was reported. Local index paths are constrained before loading, with traversal/missing-file tests. This is mitigation for the local entrypoint, not an upstream fix or a claim that every Accelerate API is safe.
- Setuptools 81: `PYSEC-2026-3447` / `CVE-2026-59890`, source-distribution manifest behavior. It satisfies PyTorch's `<82` constraint. Windows inference does not publish sdists; this is scoped non-applicability, not universal remediation.
- Local-version, CUDA and vendored packages can be skipped by package-name advisory databases. Native drivers, FFmpeg, wheels and source forks are not certified by a zero-count pip/npm scan.

See `app-advisories.json`, `model-advisories.json`, `npm-audit.json` and [runtime provenance](RUNTIME-PATCHES.md). No formal exhaustive security penetration test was completed.

## UI verification and limitations

Edge was reconnected after the reboot. The dedicated Neuro page, actual `/status` response, honest free-text deferred response, preserved draft and revised footer were inspected in the live production app. Mobile layout and link checks are recorded in the recovery screenshots. Loading follows the real request lifecycle; responses are deterministic local evidence commands, not an enabled LLM.

The app remains local and single-workspace. Kragel transfer validation, TSAM held-out calibration, licensing permissions, original-versus-quantized accuracy, full Launch acceptance and crash diagnosis remain unresolved. Public deployment, CoreWeave compute/storage, TypeSafe and W&B Inference are deferred. Historical audit documents are preserved under `docs/archive/20260910-pre-recovery`; their counts and integration states are historical only.

Final frontend build: `wQZnCiN-UvI5Tbj5alk1h`. Summary receipt: `data/verification/release/completion-after-crash.json`. Edge confirmed no horizontal overflow at390px or1490px, no floating assistant, a real18-tool MCP handshake, authenticated Weave and paused Launch. Final desktop error log contained a Grammarly extension message; no application error was observed in that inspected log. Recovered UI screenshots use the `*-recovered-*` filenames in the same evidence directory.
