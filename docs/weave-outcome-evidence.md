# Weave outcome evidence

Verified on 2026-09-13 using persisted NeuroLoop records and authenticated W&B/Weave readback.

## Readiness extension

[Current W&B export](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/runs/outcomes-747263372da12413) adds an execution-readiness chart and tables for per-run milestones and TypeSafe/engine gates. There are now ten nonempty evidence tables and four charts. No candidate-evidence table is published yet because the campaign database has no verified generated candidates.

The stricter `full_loop_verified_rate` is distinct from the earlier candidate-plus-decision completion metric: it also requires approved planning, successful vision, engine-eligible evidence and a generated child descended from a parent selected by an applied revision decision. Its denominator includes only runs with at least one attempted job. The current ladder shows three of four runs with successful control-plane jobs and completed plan reviews, zero approved plans, and zero verified generation or full loops.

Candidate eligibility reuses the engine's actual evidence rules. Required-evaluator completion alone does not imply eligibility: unknown or failed hard constraints still block it. Proposed and applied TypeSafe actions are separate; confidence floors are included. Missing candidate and final-decision denominators remain unavailable. No extra host metrics or cross-model quality averages were added.

Validation after this extension: 64 backend tests passed and the frontend TypeScript check passed. Isolated tests verify that registration does not count as execution, a decision without a generated revision child is insufficient, and missing hard-constraint checks prevent eligibility. An unrelated concurrent frontend file has an EOF whitespace warning; it was left untouched.

## Outputs

The web observability page is now named **Logs & Charts**, with a top-level sidebar entry and six sections: Overview, Execution logs, Evidence & models, Decision gates, Workers & storage, and Run history. Tables support search, sortable columns, 20-row pagination and CSV export; polling can be paused and snapshots downloaded.

The expanded authenticated API was verified against persisted data: 33 events, 46 trace records, eight capability registrations, 38 backup records and 23 standalone model receipts. Event metadata is allowlisted; raw prompts and free-form reasons are excluded. The event table is bounded to the latest 1,000 records.

[Consolidated live W&B dashboard](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/runs/neuroloop-outcomes) now receives subsequent exports using one stable run ID. Fifteen nonempty tables were published with verified readback. Existing 38 backup runs were renamed and grouped under `artifact-backups`; no evidence was deleted. W&B's accessible run links contain two text labels each, but API inspection found no duplicate run IDs or names in the original 40 records. Two older snapshot runs remain as history.

Deployment handoff: the new web production build is in `frontend/.next-observability`. The launcher supports `NEUROLOOP_BUILD_DIR=.next-observability`. The running API must also reload the new Python modules. The existing web process was not restarted. Automatic approval review rejected starting separate local preview servers without a stated reason, so browser verification of the new web layout remains pending. The currently served page was inspected and is still the older Telemetry implementation.

- [W&B charts and seven tables](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/runs/outcomes-6468d285f0914a1f)
- [Weave snapshot publication](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/01a09a34-c735-72a9-82ac-295a04687e14)
- [Research notebook](https://molab.marimo.io/notebooks/nb_73JSq6F4XRqHkTGvVzbqjS)
- [Generation notebook](https://molab.marimo.io/notebooks/nb_hmqbzUN6NR96sCQ55RKPXb)
- [Verified generation-notebook dataset read trace](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/01a09a40-be3d-7f91-bd92-7c1da4e038ca)

Both hosted notebooks now import Weave, wrap actual registry inference calls, and contain an outcome dashboard with campaign funnel and stage latency charts plus six table tabs. The refresh button queries the latest published Weave datasets. It is explicitly labeled as published evidence, not a live worker connection. Real dataset-read failures encountered during implementation remain in Weave; they are not fabricated model failures.

## Reproduce the publication

From the repository root, with privately configured W&B settings:

```powershell
.venv/Scripts/python.exe scripts/export_outcome_telemetry.py --publish
```

The script writes `artifacts/telemetry/outcome-snapshot.json` and verified publication receipts. Content hashes prevent unchanged snapshots from creating duplicate exports. W&B tables serialize nested metadata to JSON strings to preserve heterogeneous rows. An export error marks its W&B run failed; success requires remote metric readback.

The FastAPI endpoints `/api/v2/telemetry` and `/api/v2/workers/telemetry` require operator and worker authentication respectively. The web Telemetry view polls the operator endpoint every ten seconds. Its restart is intentionally left to the concurrent frontend task at the user's request.

## Recorded results and limits

The verified snapshot contains four optimization runs, seven jobs and nine attempts. Six of seven jobs succeeded on their first attempt, with a recorded attempt p95 of 271.32 seconds. The campaign funnel has zero generated candidates, decisions and explicit human acceptances. Separately recorded manual media evaluations are displayed as quality cohorts, not counted as completed campaign loops.

Three attempts have recorded token usage: 37,863 tokens in total. The remaining six attempts have no token evidence. All nine lack recorded dollar costs, so cost per acceptance and total known cost remain unavailable. Historical Weave calls did not accept token-summary enrichment through repeated call-end delivery; their actual token evidence is preserved in the new attempt dataset and W&B tables. Future completed trace deliveries include native usage summaries.

No human acceptance, quality gain, price, model result or completed loop is invented. The API supports explicit `accept` and `accept_after_edit` feedback, but no such feedback was submitted during verification. Model estimates are not measured human brain activity.

Both Molab sessions were running when checked. This does not guarantee continuous availability or resident model weights. The research worker's local-API transport was unavailable, and the generation notebook reported no connected external application. Restoring that transport and verifying a new complete generation/research/revision loop remains separate from the verified telemetry path.

Validation: 61 backend tests passed; frontend TypeScript check passed; W&B charts and both hosted notebook charts were inspected through browser controls. No frontend restart was performed after the user's instruction to leave it to the other task.
