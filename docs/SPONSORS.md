# Sponsor integrations

Updated September 11 after fresh CPU execution and actual Molab setup. No CoreWeave compute has been provisioned; Molab runs only the sanitized plotting notebook on its default CPU runtime.

| Tool | Actual state | Role |
|---|---|---|
| marimo / Molab | Local app on port 2718 and actual saved hosted notebook, browser-verified | Local live ledger; hosted sanitized snapshot with eleven chart views |
| Weave | Credentialed; actual remote traces and readback verified | Durable export of selected numerical evidence and execution metadata |
| W&B Models | Actual run metadata published | Gives ARIA real experiment context and records Launch results |
| ARIA | Actual research review completed | Inspects history and proposes a permitted next experiment |
| W&B Launch | Versioned local bridge installed; **execution paused** | Dispatches locally approved contracts through the same GPU queue; latest full job crashed |
| W&B MCP | Official server, 19 read-only tools, remote query verified | Lets terminal agents inspect W&B experiments and Weave traces |
| W&B Inference | Deferred by user; disabled | Future constrained planner; no LLM request made |
| CoreWeave compute/storage | Deferred | No provisioned cloud resources |
| TypeSafe | Deferred | No active decision-provider call |

## Weave: open the actual result

[NeuroLoop W&B project](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop).
[Fresh audio trace](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/562f0b92-9d69-46cd-bf32-8d4306ac05cf), independently read back through the official W&B MCP with matching local run/evaluation IDs.

Credentials are already in the private root `.env`; do not paste or commit them. `WANDB_PROJECT` is `entity/project` for Weave. W&B Models/Launch helpers split it into entity and project inside their process because that SDK rejects slash-containing project names.

`telemetry.py` records real run/evaluation start and end timestamps. `delivery.py` persists a SQLite outbox with stable call IDs, status, attempts, timestamps, errors and trace URL. The API drains it periodically under a file lock. A record is delivered only after finishing, flushing and reading back the ended remote call. Retries are bounded; failures remain visible and local results survive. Restored pending exports are held, not replayed automatically.

The export allowlist includes IDs, timings, decisions and numerical metrics. It excludes raw media, cortical arrays, credentials and briefs. Parent receipt IDs are metadata; no claim is made that every trace is nested in the remote UI. Open **MCP connections → Check service connections** and inspect the real receipt table. A credentials check alone is not proof of export.

## ARIA and Launch

ARIA reviewed published experiment history, including the measured contrast-up tradeoff, and supplied a bounded replication hypothesis. The actual response is saved in `data/verification/release/aria-review.txt`.

Installed job: `jerry-wen0616-santa-clara-university/neuroloop/neuroloop-bounded-v1:v0`; queue: `neuroloop-local-v1`. The uploaded artifact contains the fixed job stub and SDK requirement, not models, source media or private configuration.

`agent_bridge.py` validates version 1 proposals: source, base run, permitted operator and hypothesis. It snapshots the objective/project, caps the budget, and requires a SHA-256 review digest. `scripts/agent.py propose FILE`, `show ID`, and `submit ID --digest SHA256` expose the review sequence. Submission records intent before contacting Launch; uncertain outcomes require receipt inspection, not blind retry.

The restricted `launch_agent.py` checks job/entity/project/resource and allows only the proposal ID override. It invokes the installed local entrypoint with argv; it does not execute arbitrary downloaded source, shell commands, Docker or Git overrides. The local domain queue and GPU lock still apply. Cancellation propagates to owned work. Result receipts compare the local run ID/status with remote readback.

The first attempt was cancelled during a missing language-model dependency download; that asset is now installed and pinned. The retry completed its baseline but the reference evaluation crashed Windows. [Actual failed run](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/runs/n8jfg4uh): remote `crashed`, confirmed `local_status=failed`. **No completed ARIA-to-Launch optimization has passed acceptance.** Both standalone and supervised Launch paths honor the current hold.

ARIA and Weave serve different purposes here: ARIA proposes a research action from evidence; Weave records what actually happened. Neither replaces local evaluation or validates psychological claims.

## marimo

http://localhost:2718 is the actual local marimo application. `research/lab.py` reads the real ledger, and `research/charts.py` supplies measured change, operator outcomes, search trajectory, parallel coordinates, compute efficiency, run reliability and operator experience. Existing tables and cortical timelines remain available. Empty selections display absence of data, not fabricated examples.

The actual [Molab notebook](https://molab.marimo.io/notebooks/nb_B79BrKA5Rh4UNJxj9NQ1kf) was created, executed, saved and browser-verified in the user's account. It contains sanitized historical numerical records and the fresh TSAM CPU result across eleven chart views. No project database, source media or credentials were uploaded. This is a snapshot, not an automatic connection to the local database. See [MOLAB.md](MOLAB.md).

## Deferred integrations

`NEUROLOOP_PLANNER_ENABLED=false` remains in effect. W&B Inference will be connected later; no paid planner request or free-form chat model is enabled. The dedicated Neuro page runs documented local evidence commands and links to MCP. Kragel and TSAM adapters and assets are present on this Windows disk; current capabilities report experimental readiness, with scientific validation still unpassed. See CURRENT-INTEGRATION-AUDIT.md for recomputed hashes and registration limitations. CoreWeave generation/compute, Ideogram 4, MiniMax H3 and TypeSafe remain unavailable until the corresponding access is actually configured.

Official references: [Weave](https://docs.wandb.ai/weave/quickstart), [ARIA](https://docs.wandb.ai/aria/overview), [Launch](https://docs.wandb.ai/platform/launch/create-and-deploy-jobs), [W&B MCP](https://github.com/wandb/wandb-mcp-server), [marimo plotting](https://docs.marimo.io/api/plotting/).

## September 11 build boundary

The response-target loop does not depend on sponsor generation credits. Local controlled
interventions, TRIBE, the experiment ledger, website and NeuroLoop MCP retain the
TRIBE-only workflow. Kragel and TSAM are optional experimental branches. Their local assets are present; their scientific validation and registration requirements remain open.

Sponsor-dependent creative generation is deliberately not claimed as implemented:

| Provider | Current state | Activation condition |
|---|---|---|
| Ideogram 4 | `awaiting_sponsor_access` provider boundary only | Sponsor credits/API access supplied and a live contract test passes |
| MiniMax H3 | `awaiting_sponsor_access` provider boundary only | Sponsor credits/model access supplied and a live contract test passes |
| CoreWeave compute | `awaiting_sponsor_credits` | Provisioned resource plus tested deployment |

The rest of the sponsor/service boundary remains explicit:

| Service | Current use | Partner requirement |
|---|---|---|
| W&B Weave | Exports selected execution metadata and numerical results; prior remote verification recorded | Own W&B API key and writable project |
| W&B Models | Stores experiment metadata used by research/Launch | W&B account/project |
| CoreWeave ARIA | Reviewed actual experiment history; optional for local inference | Own ARIA access |
| W&B Launch | Restricted bridge to the same local experiment queue; full workflow acceptance remains unfinished | Configured job, queue and local agent |
| W&B MCP | Official read-only tools for W&B records | Own W&B credentials |
| NeuroLoop MCP | Same domain services and ledger as the website | Local server/client configuration; no paid model API required |
| marimo | Local research notebook, charts and tables | Local installation only |

A sponsor name in the UI is never treated as evidence that the connection works. Runtime
status and receipts are the source of truth.
