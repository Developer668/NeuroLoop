# Evidence dashboard and hosted notebook receipts

Open `http://localhost:3010/workspace?view=brain`. Brain Lab reads persisted campaign evaluations and separately attributed notebook imports every five seconds. The exact input SHA-256 accompanies each receipt. Selecting an output shows its own media, generator provenance, GLM review, TRIBE response, TSAM windows, Kragel diagnostics, model inventory, logs, and W&B delivery receipts when available.

Video time selects the corresponding stored cortical frame. The timeline uses the model's recorded timestamps, not an invented animation. Region summaries use the installed fsaverage5 atlas and report native response units. A still image gets its actual vision review; the current research adapter does not silently turn it into a simulated viewer experiment.

## Notebook integration

Campaign workers continue to upload leased job results through the existing job endpoints. Those evaluations appear automatically in Brain Lab. Independently executed notebook checks can POST multipart metadata and an optional real `cortical.npz` to `/api/v2/workers/evidence`, using the existing worker bearer credential. The typed receipt requires an existing input asset, its exact SHA-256, a stable source receipt ID, source classification, and actual model provenance. Cortical bytes are decoded and validated. Reusing a receipt ID with different content is rejected.

`NotebookEvidence` is separate from campaign decisions. Importing a reference test or an operator-directed generation never advances a campaign, grants eligibility, or bypasses TypeSafe. A recorded revision must cite evidence evaluating its actual parent asset. Ideogram alternatives are labeled text alternatives because the model does not consume the parent's image pixels.

`notebook_verification.evaluate_ads` performs real GLM media review and publishes validated receipts. `summarize_ads` reads the saved evidence and run state, asks the configured W&B model for a summary, validates its cited IDs, and persists the provider receipt. Invalid provider responses remain failures. Video observations now cite zero-based supplied frame indices; the client attaches exact sampled timestamps.

`/api/v2/workers/application-runtime` serves only application Python source to authenticated workers. It does not contain secrets, model weights, or notebook documents. A live notebook must reload the updated configuration class as well as the adapter when adopting a new runtime schema.

## Storage

- Local immutable assets: `data/v2/objects`.
- Database, events, jobs, evaluations, notebook evidence and export state: `data/v2/neuroloop.sqlite3` for this development installation.
- API logs: `data/logs/api-molab.out.log` and `api-molab.err.log`.
- Frontend logs: `data/logs/frontend-local.out.log` and `frontend-local.err.log`.
- Exportable live run history: `/api/v2/runs/{run_id}/export` through the authenticated web proxy.

Weave stores structured call traces and failure history. Install the `telemetry` extra and set `NEUROLOOP_WANDB_ARTIFACTS_ENABLED=true` to additionally back up original media, generated files, cortical arrays, receipts and run snapshots as W&B artifacts. This is opt-in because it uploads user content. `WANDB_PROJECT` must be `entity/project`. The queue retries failed uploads, reconciles existing content, verifies the remote manifest and source checksum, and exposes confirmed links at `/api/v2/backups`. Inference does not wait for exports.

Production database deployments must run `alembic upgrade head`; new migrations add the notebook evidence and artifact backup tables. Development `create_all` adds new tables without changing old results.

## Limits that remain visible

TRIBE and TSAM are model proxies, not measured human responses or validated advertising outcome predictions. Kragel diagnostics with unverified registration cannot drive decisions. Installed checkpoint files do not prove a model was invoked. TypeSafe low-confidence stops remain stops even when a choice says APPROVE. Hosted notebook availability is controlled by Molab; this dashboard does not guarantee continuous 24/7 GPU uptime or prevent provider shutdown.
