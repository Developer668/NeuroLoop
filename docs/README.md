# NeuroLoop documentation

Updated September 10, 2026 for the GitHub source handoff. This index summarizes the recorded recovery audit; the documentation/push operation did not rerun inference or establish a new stability result.

## Current completion status

| Area | Completed | Still open |
|---|---|---|
| Product and UI | Landing page, animated footer, workspace, anatomical brain, evidence charts and dedicated Neuro command page | Free-form AI conversation is deferred; the new flat assistant PNG is an available asset, not the currently wired artwork |
| Local backend | Real media processing, saved TRIBE predictions, bounded edit queue, scoring, API and MCP | GPU execution is held after repeated Windows graphics crashes |
| Engineering | Isolated pinned runtimes, guards, migrations, backup/restore, 109 passing backend tests and production frontend build recorded | Second-installation full inference, repeat stability and broader operational acceptance |
| Research | Real ledger, seven marimo experiment plots, tables and cortical timelines | Quantization accuracy, Kragel transfer validation, TSAM domain validation and commercial permissions |
| Sponsors | Verified Weave export/readback, W&B metadata and read-only MCP, actual ARIA review | Full Launch experiment acceptance failed during the crash; Inference, cloud compute/storage and TypeSafe remain deferred |

The recorded recovery audit passed 16 checks and verified 29 saved arrays and 32 managed media hashes. These are actual saved outputs; they do not validate emotion decoding or certify production readiness. Review services remain usable while model execution is paused.

## Current documents

| Document | Read it for |
|---|---|
| [Main README](../README.md) | Product overview, local URLs, folder map and source-installation boundaries |
| [Architecture](ARCHITECTURE.md) | Frontend/backend responsibilities, models, storage, execution and acceptance flow |
| [Audit results](AUDIT.md) | Passed checks, real output identifiers, failed gates and evidence locations |
| [Remaining work](REMAINING-WORK.md) | Unfinished work and the evidence required to close each item |
| [Sponsor integrations](SPONSORS.md) | What is connected, what is paused, real remote links and metadata sharing |
| [MCP and services](CONNECTIONS.md) | Local agent configuration, endpoints and connection verification |
| [Crash recovery](CRASH-RECOVERY.md) | Graphics crash evidence, execution hold and diagnosis handoff |
| [Request reconciliation](REQUEST-RECONCILIATION.md) | Implemented, adapted, blocked and deferred user requests |
| [Runtime patches](RUNTIME-PATCHES.md) | Pinned dependencies, vendored modifications and advisory caveats |
| [Scientific handoff](RESOLUTION-HANDOFF.md) | Kragel/TSAM access and validation requirements |
| [Model compatibility](MODEL-COMPATIBILITY.md) | Model interpretation and earlier compatibility evidence, subject to the current hold |
| [Brand](BRAND.md) | Logo, colors and assistant asset status |
| [Session memory](PROJECT-STATE.md) | Compact state for the next development session |

## Historical planning and evidence

[Build plan](BUILD-PLAN.md), [implementation plan](IMPLEMENTATION-PLAN.md), [design refinement](REFINEMENT.md) and [earlier validation](VALIDATION.md) retain design decisions and preceding checks. They are not the current release verdict. [Archived pre-recovery documents](archive/20260910-pre-recovery/README.md) preserve the earlier state; the current audit and remaining-work list take precedence.

## Evidence and publication boundaries

GitHub includes the source and these human-readable findings. Raw audit receipts, SQLite records, media, weights and local credentials remain on the original computer under the documented paths and are excluded from Git. A saved test report is historical evidence, not proof that a fresh clone or a currently stopped service works. No GPU workload was restarted to publish this handoff.
