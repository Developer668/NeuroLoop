# NeuroLoop

A local creative research application built around real, frozen TRIBE v2 inference.
Upload media, inspect predicted cortical responses, compare creatives and run
bounded edits against an explicit numerical reference objective. The UI, HTTP API
and MCP interface share the same persistent state and execution engine.

**Current status: local functionality verified; production release is not yet
cleared.** The latest audit found Python dependency conflicts and advisory matches.
Kragel, scientific validation, external sponsor setup and the original graphics
crash diagnosis also remain open. Read the audit before making production claims.

## Start here

| Document | What it explains |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Complete runtime/data flow, folder map, model pipeline, storage, optimization and access boundaries |
| [System audit](docs/AUDIT.md) | Fresh checks, actual output proof, dependency findings and audit limits |
| [Remaining work](docs/REMAINING-WORK.md) | Priorities and evidence required to close each release gate |
| [Sponsor integrations](docs/SPONSORS.md) | Implemented vs connected services, credentials, data sharing and missing code |
| [Kragel/TSAM handoff](docs/RESOLUTION-HANDOFF.md) | Source links, maintainer contacts, exact information to request and validation requirements |
| [MCP connections](docs/CONNECTIONS.md) | Configured Codex command and authenticated HTTP setup |
| [Project state](docs/PROJECT-STATE.md) | Compact handoff for the next work session |
| [Model compatibility](docs/MODEL-COMPATIBILITY.md) | Quantization, TSAM technical status, anatomy and scientific boundaries |
| [Model inventory](models/README.md) | Local downloads, folders, junctions and upstream sources |

## Open the app

All application files, models and outputs live under **D:\NeuroLoop**.
Double-click **Start-NeuroLoop.cmd**. It starts the website, API, single worker and
marimo, checks readiness, then opens the workspace. Keep the launcher open.
Choose **Connect to this computer** in the website. If already running, use the link.

| Service | Address |
|---|---|
| Landing page | http://localhost:3010 |
| Workspace | http://localhost:3010/workspace |
| API health | http://127.0.0.1:8010/health |
| Authenticated MCP HTTP | http://127.0.0.1:8010/mcp/ |
| Local marimo research | http://localhost:2718 |

**Status-NeuroLoop.cmd** checks services. **Stop-NeuroLoop.cmd** stops only owned
processes. Startup refuses occupied ports instead of terminating other programs.
Services bind to loopback. This is one local workspace, not a public account system.

## Use a real workflow

1. Add a video, audio recording, photo or UTF-8 text file to the library.
2. Create a project and choose its source. For comparison/optimization, add reference
   assets that represent the numerical target you intend to investigate.
3. Run analysis. Speech uses local transcription or supplied timed words. Text
   requires supplied word timing; images require explicit experimental presentation.
4. Open Brain Lab for the saved surface, timeline, anatomical regions and numerical
   provenance. The 20,484 surface vertices are not individual neurons.
5. Compare compatible model profiles or run a permitted edit under a fixed budget.
   Inspect the measured decision and download the creative plus actual evidence.

Scores measure predicted cortical-pattern similarity. They do not measure liking,
conversion, emotion probability or a particular person's response. No model weights
are trained and no human-feedback RLHF is used. Edit statistics adapt within context.

## What is built

- Next.js/React UI: landing, login, projects, library, comparison, experiments,
  Brain Lab, research, preferences and MCP/service connections.
- FastAPI backend, durable SQLite queue/events, managed media, FFmpeg compositions
  and bounded edits, evidence/cache storage and ZIP export.
- Actual TRIBE prediction with local INT8 video, NF4 base Llama text and official
  Wav2Vec-BERT audio encoders. DINOv2 is downloaded but inactive in this configuration.
- Anatomical fsaverage5 brain and 148 Destrieux parcels; actual saved-value coloring.
- Optional independent TSAM CPU inference with eight signed, experimental logits.
- Fifteen MCP tools and a running local marimo research app.
- Serialized execution, GPU/RAM headroom checks, time limits, cancellation, owned
  subprocesses and recovery that preserves evidence without automatically replaying
  an interrupted job. Each evaluation exits to release model allocations.

Weave and W&B Inference have implemented optional code paths, but no credentialed
remote call is verified. ARIA still needs its Launch job/result bridge. CoreWeave
compute is deferred; TypeSafe is disabled. These are not finished integrations.

## Proof of actual output

The fresh system audit invoked MCP, rendered a source-derived NASA composition,
queued a new neural evaluation, and obtained a **6 x 20,484** cortical array in
**44.36 seconds**. All **27 recorded arrays** matched recomputed summaries and API
frames; all **31 managed assets** matched stored hashes. Earlier tests cover raw
NASA video, audio, photo presentation and a measured controlled-edit tradeoff.

[Open the audited result](http://localhost:3010/workspace?view=brain&evaluation=637922a4-b133-412a-9b81-ab028b042382).
[Download the local evidence ZIP](data/verification/system-audit/fresh-output.zip).
The ZIP contains `prediction.npy`, evidence and the selected creative, not just
screenshots or a successful HTTP response. Model-feature caches can be reused;
this is not a cold-start performance or scientific-accuracy benchmark.

The latest suite passed **70 backend tests**, the production frontend build and
Edge interaction/responsive checks. npm reported zero known advisories. Python
checks did not pass: both environments inherit global packages; see the audit.

## Folder map

```text
D:\NeuroLoop\
  frontend/src/                UI, routes, API proxy and styles
  backend/neuroloop/           API, domain logic, worker, models and MCP adapters
  models/                     Feature weights, readout sources and download manifests
  tribev2-balanced-qv-local/   Original TRIBE checkpoint, INT8 video and model runtime
  research/                   marimo ledger and charts
  scripts/                    Launchers, setup and verification utilities
  data/                       SQLite, media, predictions, logs, exports and receipts
  docs/                       Architecture, status, audit and handoff guides
  .venv/                      App runtime; currently inherits system packages
  .env                        Private configuration; never share its contents
```

Do not move junction targets or delete the database to repair a crash. Previous
technical fixture projects are archived; their actual data remains accessible in
research history. Backups are under `data/build-backups`.

## MCP

The local `neuroloop` entry is already configured in Codex. Inspect it with:

```powershell
codex mcp get neuroloop
```

Its stdio command is `.venv\Scripts\python.exe scripts\mcp_stdio.py` with absolute
paths in the configuration. Reload MCP connections or reopen Codex to discover it.
The audit connected through the real SDK over both stdio and HTTP. Configuration
alone does not retroactively add tools to an existing conversation.

## Verification commands

```powershell
Set-Location D:\NeuroLoop
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe scripts/audit_system.py
.\.venv\Scripts\python.exe scripts/verify_refinement.py
```

The audit script deliberately creates one named source-derived composition/project
and performs a fresh GPU evaluation. Run inference checks serially. For frontend
builds, stop NeuroLoop first, then run `npm.cmd run build` inside `frontend`, and
restart afterward. Detailed receipts are in `data/verification/system-audit`.

## Stability and release limits

The Windows `VIDEO_DXGKRNL_FATAL_ERROR (0x113)` root cause is unresolved; no driver,
registry, firmware or power settings were changed. A completed run and memory
pressure controls cannot guarantee graphics-driver stability. Kragel requires
registration/scoring/transfer validation; TSAM requires scientific validation and
appropriate permissions. Commercial use must satisfy upstream terms.

Follow [Remaining work](docs/REMAINING-WORK.md) to close these items. Do not interpret
this README as a claim that every planned feature or sponsor connection is complete.
