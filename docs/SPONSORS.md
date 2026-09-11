# Sponsor integrations

Status after the September 10 crash recovery. No cloud compute has been provisioned.

| Tool | Actual state | Role |
|---|---|---|
| marimo | Local app on port 2718, browser-verified | Reads real SQLite records, saved cortical timelines and experiment charts |
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
[Verified trace](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/1c6d3e1b-1a09-4eae-b6a8-84490afff8c6).

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

http://localhost:2718 is the actual local marimo application. `research/lab.py` reads the real ledger, and `research/charts.py` supplies measured change, operator outcomes, search trajectory, parallel coordinates, compute efficiency, run reliability and operator experience. Existing tables and cortical timelines remain available. Empty selections display absence of data, not fabricated examples. Molab tutorials informed plotting; no project database or source media was uploaded to Molab.

## Deferred integrations

`NEUROLOOP_PLANNER_ENABLED=false` remains in effect. W&B Inference will be connected later; no paid planner request or free-form chat model is enabled. The dedicated Neuro page runs documented local evidence commands and links to MCP. CoreWeave compute/storage, TypeSafe, Kragel activation and TSAM scientific validation remain deferred as requested.

Official references: [Weave](https://docs.wandb.ai/weave/quickstart), [ARIA](https://docs.wandb.ai/aria/overview), [Launch](https://docs.wandb.ai/platform/launch/create-and-deploy-jobs), [W&B MCP](https://github.com/wandb/wandb-mcp-server), [marimo plotting](https://docs.marimo.io/api/plotting/).
