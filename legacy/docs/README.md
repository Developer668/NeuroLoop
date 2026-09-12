# NeuroLoop documentation

Latest architecture comparison: [three-loop source audit and complete checklist](THREE-LOOP-AUDIT.md).

Latest review: [current and proposed agentic loop](AGENTIC-LOOP-REVIEW.md), including the verified Weave failure-classification correction, and [scientific validation audit](SCIENTIFIC-VALIDATION-AUDIT.md), including the published TSAM split checks and unresolved provenance.

Verification for those changes: [build, backend tests, Edge playback and remote Weave readback](LOOP-REVIEW-VERIFICATION.md).

Latest UI and remote-branch check: [branch comparison, display changes and verification](BRANCH-AND-DISPLAY-REVIEW.md). The fetched branch matches local HEAD; newer local fixes remain uncommitted. Molab was stopped and its dashboard reported Running 0.

Latest: [fresh execution and UI verification](FRESH-EXECUTION.md), [actual Molab notebook](MOLAB.md), [Kragel registration requirements](KRAGEL-REGISTRATION.md), and [current graphics-crash diagnosis](CRASH-DIAGNOSIS-CURRENT.md).

Updated September 11, 2026 after the UI, media and MCP refresh. The live library was cleared after backup. GPU inference remains paused.

## Current completion status

| Area | Completed | Still open |
|---|---|---|
| Product and UI | Landing page, animated footer, workspace, anatomical brain, evidence charts and dedicated Neuro command page | Free-form AI conversation is deferred; the supplied flat assistant artwork is wired; scientific readouts remain experimental |
| Local backend | Real media processing, saved TRIBE predictions, bounded edit queue, scoring, API and MCP | GPU execution is held after repeated Windows graphics crashes |
| Engineering | Isolated pinned runtimes, guards, migrations, backup/restore, fresh CPU inference and production frontend build; latest checks in FRESH-EXECUTION.md | GPU repeat stability and broader operational acceptance |
| Research | Real live ledger, local marimo plots, actual hosted Molab notebook with eleven chart views, tables and cortical timelines | Quantization accuracy, Kragel transfer validation, TSAM domain validation and commercial permissions |
| Sponsors | Verified Weave export/readback, W&B metadata and read-only MCP, actual ARIA review | Full Launch experiment acceptance failed during the crash; Inference, cloud compute/storage and TypeSafe remain deferred |

The recorded recovery audit passed 16 checks and verified 29 saved arrays and 32 managed media hashes. These are actual saved outputs; they do not validate emotion decoding or certify production readiness. Review services remain usable while model execution is paused.

## Current documents

| Document | Read it for |
|---|---|
| [Main README](../README.md) | Product overview, local URLs, folder map and source-installation boundaries |
| [Architecture](ARCHITECTURE.md) | Frontend/backend responsibilities, models, storage, execution and acceptance flow |
| [Latest refresh verification](REFRESH-VERIFICATION.md) | Fresh media/MCP checks, browser checks, cleanup and limits |
| [Current integration audit](CURRENT-INTEGRATION-AUDIT.md) | Sponsor readbacks, model hashes and scientific caveats |
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
