# NeuroLoop

A local creative research workspace with real TRIBE v2 predictions, controlled media edits, cortical visualization and an auditable experiment ledger. The website and MCP clients use the same services, data and execution rules.

**September 10, 2026 recovery status: the application is available for evidence review; GPU inference and Launch execution are paused after another Windows graphics crash. Production release is not cleared.** The crash cause has not been diagnosed. Reopening the app does not restart the failed workload.

## Open the application

On Windows, double-click `D:\NeuroLoop\Start-NeuroLoop.cmd`. On Apple Silicon macOS, run `./Start-NeuroLoop.sh` from the repository folder. Choose **Connect to this computer** if prompted. The launcher starts the website, API and local marimo app. The Mac launcher uses the MPS inference backend for an explicitly requested local stability test and keeps the original Windows crash hold record; the Windows launcher continues to honor that hold and omits the model worker and Launch agent.

| Page | Address |
|---|---|
| Landing page and animated footer | http://localhost:3010 |
| Workspace | http://localhost:3010/workspace |
| Dedicated Neuro assistant page | http://localhost:3010/neuro |
| MCP connections and sponsor receipts | http://localhost:3010/workspace?view=connections |
| Local marimo research | http://localhost:2718 |
| API health | http://127.0.0.1:8010/health |
| Authenticated MCP HTTP | http://127.0.0.1:8010/mcp/ |

`Stop-NeuroLoop.cmd` requests shutdown of owned processes. `Status-NeuroLoop.cmd` checks listening services. Services bind to loopback; this is one local workspace, not a public account system.

## What is implemented

- Next.js/React landing, library, projects, comparisons, experiments, anatomical Brain Lab, research, settings and connections. A dedicated Neuro page replaces the floating assistant.
- Neuro's generated ribbon artwork and SVG mark; autosizing session draft; five real local evidence commands; animated pixel loading during requests. Free-form AI conversation remains deferred, as requested. No microphone, model selector or invented AI response is represented as working.
- Animated background paths, cinematic footer reveal, moving typography, pointer-responsive workspace link, responsive layouts and reduced-motion support.
- FastAPI services, SQLite queue/events, managed uploads, FFmpeg compositions and bounded edits, numerical acceptance rules, versioned caches and actual evidence ZIPs.
- Locally quantized TRIBE pipeline: INT8 V-JEPA2, NF4 base Llama-3.2-3B, official Wav2Vec-BERT audio and original TRIBE brain checkpoint. DINOv2 is downloaded but inactive in this feature configuration.
- Anatomical fsaverage5 surface with 20,484 vertices and 148 Destrieux parcels; saved response coloring, timelines and comparison overlays. These vertices are not individual neurons.
- Eighteen NeuroLoop MCP tools; an official W&B MCP server with 19 read-only tools; a local marimo notebook with seven experiment plots plus tables and cortical timelines.
- Credentialed Weave with remotely verified trace receipts and a durable retry outbox. An ARIA review of real W&B results and a versioned, restricted local Launch adapter exist. The full Launch experiment failed during the graphics crash and is not accepted as completed.
- Isolated pinned runtimes, versioned database migrations, session revocation, backup/restore tooling, owned-process cancellation and a persistent execution hold.

## Actual evidence

The isolated runtime completed a new MCP-driven silent NASA composition evaluation: **6 × 20,484 values in 42.485 seconds**, evaluation `cdfaacce-e365-4eca-8447-ba323c64d5e5`. A later audiovisual baseline completed in **89.437 seconds**; its reference evaluation was interrupted by the Windows crash. Neither timing is a general cold-start benchmark.

[Open the completed isolated-runtime result](http://localhost:3010/workspace?view=brain&evaluation=cdfaacce-e365-4eca-8447-ba323c64d5e5).

The post-crash audit checked **29 saved arrays and 32 managed media files**: all array summaries, served first frames and asset hashes matched. **109 backend tests passed**, the frontend production build passed, and the recovery audit passed all 16 checks without neural execution. See [AUDIT.md](docs/AUDIT.md) for evidence and limitations.

Scores measure similarity between predicted cortical patterns. They do not establish emotion, liking, conversion or a particular person's response. Model weights remain frozen; only context-specific edit statistics adapt. Kragel and TSAM scientific validation are deferred to the user. Commercial permissions and quantization accuracy validation remain open.

## Folder map

```text
D:\NeuroLoop\
  frontend/src/                 Routes, React components, browser API and styles
  frontend/public/brand/        NeuroLoop logo, Neuro PNG artwork and SVG mark
  backend/neuroloop/            API, domain services, queue, inference, MCP, guards
  infrastructure/runtime/      Runtime inputs and pinned locks
  infrastructure/vendor/       Explicit local packaging forks and official MCP source
  infrastructure/launch/       Installed versioned W&B job/queue manifest
  infrastructure/wheels/       Verified spaCy language wheel recovery asset
  .runtimes/                   Isolated app, model, W&B MCP and rehearsal environments
  models/                      Encoders, scientific readout sources and loader
  tribev2-balanced-qv-local/    Original TRIBE checkpoint and local INT8 video weights
  research/                    marimo app and charts
  scripts/                     Lifecycle, audit, recovery, backup and Launch tools
  data/                        Database, media, arrays, receipts, logs and backups
  docs/                        Architecture, audit, remaining gates and handoff
  .env                         Private credentials; never publish
```

The old `.venv` directories are preserved for rollback, not used by the active service configuration. Some model folders are junctions: do not move their targets. Do not delete the database, caches or execution-hold file as a crash workaround.

## Read the handoff

Start with the [documentation index and completion status](docs/README.md). All project-wide architecture, audit, sponsor, recovery and remaining-work documents are collected in `docs/`. Older plans and audit snapshots are explicitly historical.

| Document | Purpose |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Runtime, model, data and acceptance flow |
| [Audit](docs/AUDIT.md) | Current verified facts and failed gates |
| [Request reconciliation](docs/REQUEST-RECONCILIATION.md) | What was implemented, adapted, deferred or remains blocked |
| [Crash recovery](docs/CRASH-RECOVERY.md) | Crash evidence, hold behavior and dump-analysis handoff |
| [Remaining work](docs/REMAINING-WORK.md) | Evidence still required before release |
| [Sponsors](docs/SPONSORS.md) | Actual integration state, remote links and metadata contracts |
| [Connections](docs/CONNECTIONS.md) | Codex, other MCP clients and verification |
| [Runtime patches](docs/RUNTIME-PATCHES.md) | Locks, packaging forks, advisories and reproducibility limits |
| [Scientific handoff](docs/RESOLUTION-HANDOFF.md) | Kragel/TSAM links and validation requirements |
| [Project state](docs/PROJECT-STATE.md) | Compact next-session memory |

## GitHub source and local installation

This repository contains application source, model download/quantization scripts, pinned runtime inputs, vendored runtime source and licenses, brand assets and documentation. It does **not** contain downloaded model weights, Python environments, `.env` credentials, the local SQLite database, uploaded media, saved predictions, crash dumps or private audit receipts. Paths under `data/` in the audit refer to evidence on the original computer, not downloadable GitHub attachments.

The local model bundle from the companion NeuroLoop 2 folder has been restored into the paths used by this checkout. Run `python scripts/verify_local_assets.py` to verify it without starting inference. The large licensed weights remain ignored by Git, so they survive pulls and do not create merge conflicts; a fresh clone still needs the asset bundle or the pinned download scripts. See [the partner setup guide](PARTNER-START-HERE.md) and [local asset handoff](docs/LOCAL-ASSETS.md) for the exact boundary.

A fresh clone is not a ready-to-run installation. Restore or obtain the permitted model assets, provision the pinned runtimes using [runtime documentation](docs/RUNTIME-PATCHES.md), configure private local settings and follow [connection setup](docs/CONNECTIONS.md). The existing laptop remains under the [execution hold](docs/CRASH-RECOVERY.md); publishing source does not clear that hold or any release gate.

## Verify without running a model

```powershell
Set-Location D:\NeuroLoop
.\.runtimes\app\Scripts\python.exe -m pytest backend/tests -q
.\.runtimes\app\Scripts\python.exe scripts/verify_recovery.py
.\.runtimes\app\Scripts\python.exe scripts/verify_wandb_mcp.py
```

The recovery check expects the current execution hold and running review services. It validates MCP, authentication and existing outputs. **Do not run `audit_system.py` or GPU verification scripts during this hold:** those are fresh-inference workflows. For frontend changes, stop owned services, run `npm.cmd run build` in `frontend`, then restart.
