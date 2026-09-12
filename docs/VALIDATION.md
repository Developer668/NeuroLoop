> Historical plan/verification. Current recovery status and actual completed work are in [AUDIT.md](AUDIT.md) and [REQUEST-RECONCILIATION.md](REQUEST-RECONCILIATION.md). GPU execution is currently paused.

> Latest status: [System audit](AUDIT.md). The later audit found Python dependency and advisory release blockers. This page preserves the preceding refinement results and its earlier build ID.

# Earlier refinement verification — September 10, 2026

The refined application is running at http://localhost:3010; the workspace is
http://localhost:3010/workspace. All files and recorded evidence remain under
`D:/NeuroLoop`. The current receipt is `data/verification/completion.json`.

## Current checks

| Check | Result |
|---|---|
| Backend regression suite | 70 passed after the per-evaluation process change; one existing python_multipart deprecation warning |
| Next.js production build and TypeScript | Passed; build `Ak51GDzGEpZNz31M2YTFi` |
| Temporary Edge | Login, SVG profile, navigation, real comparison, incompatible selection, anatomy modes, hemisphere spacing, timeline, regions, TSAM display, research charts/tables, archived history, MCP schemas, sponsor checks and sign-out passed |
| Brain failure regression | Real geometry delayed 6.2 seconds still loads; one deliberately aborted frame request recovers via a clickable retry button |
| Responsive layouts | Landing, Brain Lab, Compare, Research and Connections at 390 and 768 px passed without horizontal overflow |
| Browser JavaScript errors | None reported in the completed interaction suite |
| Archived evidence | Archived Brain Lab link loads the saved response and original asset |
| MCP | All 15 tools exercised through the actual stdio command configured in Codex |
| Real media | NASA Apollo 11 video, recorded speech and photograph completed local TRIBE inference |
| Controlled experiment | Real contrast edit evaluated; candidate scored 0.563 vs baseline 0.570; tradeoff recorded and original retained |
| Comparison | HTTP and MCP matrices match; cross-video similarity 0.5695114161 |
| Export/render/cancel | Real composition rendered, 3,128,418-byte evidence ZIP downloaded, queued optimization cancelled |
| marimo | Local service returned HTTP 200; styled ledger, cortical traces and compute tab verified in Edge |
| Final health | API, website and research returned HTTP 200; SQLite integrity OK; zero queued/running jobs |

The browser uses a separate temporary Edge session authorized by the user, with
software WebGL. It does not use the normal Edge profile. Final desktop screenshots
of Brain Lab, comparison and research, plus responsive landing captures, were
visually inspected. Testing caught and fixed a retry button inheriting
`pointer-events: none` from the brain message overlay.

## Recorded neural evaluations

| Input | Cortical output | Recorded evaluation time | Peak PyTorch allocation |
|---|---|---|---|
| 10-second Apollo video with speech | 11 × 20,484 | 76.69 s | 2.81 GiB |
| Independent reference video | 11 × 20,484 | 30.38 s | 0.70 GiB |
| Armstrong audio recording | 13 × 20,484 | 29.47 s | 2.81 GiB |
| Lunar photograph, explicit eight-second repeated-frame presentation | 8 × 20,484 | 43.28 s | 2.78 GiB |

Video TSAM inference produced two complete five-second windows with eight signed
logits on CPU. Feature caches were reused where applicable; times are not
cold-start benchmarks. Recorded allocation excludes some driver allocations.
The video-plus-reference run completed in 106.64 seconds of recorded compute.

The first real multi-candidate attempt hit the RAM headroom guard because models
remained allocated between evaluations. Each evaluation now runs in its own owned
child process, reclaiming those allocations on exit. Subsequent video/reference
and controlled-edit runs completed. The earlier failed run remains recorded.

## Evidence and reproducibility

- `data/verification/refinement/real-media-report.json`: actual MCP calls, runs,
  numerical evidence, comparison, render, export, cancellation and service checks.
- `data/verification/refinement/real-media/sources.json`: NASA URLs and SHA-256 hashes.
- `data/verification/refinement/browser/interaction-report.json`: passing UI checks.
- `data/verification/refinement/browser/*-final.png`: final UI captures.
- `data/verification/refinement/final-health.json`: services, database and archive check.
- `scripts/audit_system.py`: active cross-platform release audit.
- `scripts/verify_real_media.py`: historical/resumable real-media verification workflow.

The 17 earlier fixture projects are archived, with original records/media retained
for research. The cleanup manifest is `data/verification/refinement/archived-records.json`.
A pre-cleanup SQLite backup and previous completion/validation receipts are in
`data/build-backups`. Prior modality, optimization and worker lifecycle checks
remain historical evidence under `data/verification`; they were not all rerun as
part of this refinement.

## Practical and scientific limits

These tests establish local software integration, not advertising effectiveness,
measured human emotions, or quantized neuroscience accuracy. Static-image
presentation is explicitly experimental. No mock neural values were substituted.

The original Windows `VIDEO_DXGKRNL_FATAL_ERROR (0x113)` is **not diagnosed or
proven cured**. Its crash dump was inaccessible. No driver, registry, firmware or
power settings were changed. Serialized inference, RAM/GPU headroom checks,
CPU offloading and process isolation reduce software pressure; they cannot
promise graphics-driver stability for arbitrary workloads.

TSAM is technically working, experimental and uncalibrated. Kragel now has a
documented MNI-volume-to-fsaverage5 projection and experimental scoring path. In
response-target runs these sources can contribute through the explicit versioned
ensemble; this establishes software integration, not human-response validity. Transfer
validation remains open. W&B and sponsor connection status is reported from the live
deployment rather than inferred from sponsor presence. CoreWeave generation/compute
remains deferred until access is actually configured.

Codex's `neuroloop` MCP entry is configured. The exact command passed SDK checks;
reload MCP connections or reopen Codex to expose it in a new conversation. This
is a verified local single-workspace build, not certification of a public,
multi-user production service.
