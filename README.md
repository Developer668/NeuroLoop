# NeuroLoop

A durable, evidence-driven advertising creative loop with a single shared model notebook.

## Current delivery
The active application is `backend/neuroloop_app` plus the new `/workspace` frontend. Source from NeuroLoopV1 is preserved separately; `backend/neuroloop` is legacy, not the application to launch. The new runtime does not start V1 GPU workers, copy V1 credentials, or download model checkpoints.

The V1 landing page and workspace design now wrap the current API: campaign overview, projects, media library, comparisons, Neuro composer, lineage, Brain Lab and connections. The composer accepts text and multiple media files, and queues a bounded run. Existing donor components remain preserved.

NeuroLab includes lazy H3 FP8 / Ideogram FP8 adapters, a real-media W&B vision adapter, and isolated bridges to the preserved TSAM/TRIBE implementations. See [self-hosted notebook setup](docs/SELF_HOSTED_NOTEBOOK.md). Model registration is distinct from successful execution. The user-selected runtime is the molab FP8 Media Studio. GLM-5.3-Flash vision/planning, TypeSafe plan approval, and Weave readback have passed live verification; the complete GPU loop is still unverified. See [the architecture audit](docs/AGENT_ARCHITECTURE_AUDIT.md).

Implemented: typed campaigns and source-aware brand constraints, real uploads, immutable artifact storage, bounded regeneration trees, durable job leases, a shared notebook model registry, W&B Inference planning, real TypeSafe structured decisions, multi-fidelity evidence, human feedback, Weave trace outbox/readback, cortical visualization, paused-only Meta deployment/insights, restricted MCP, marimo NeuroLab, migrations and CPU tests.

**Not established:** successful live H3/image/TSAM/TRIBE execution through the complete new loop, commercial lift, GPU fit/latency, or production deployment. ARIA is an honest history-export/proposal-import workflow; no undocumented ARIA API or autonomous policy activation is invented. See `docs/LIMITATIONS.md` and `docs/VERIFICATION.md`.

## Run on this Windows workspace

```powershell
cd D:\NeuroLoop
.\.venv\Scripts\python.exe scripts\start.py
```

The local setup creates ignored `.env` and `frontend/.env.local` files with new private credentials. Never copy those into a public notebook. Default UI: `http://localhost:3010/workspace`; API: `http://127.0.0.1:8010`; API schema: `/docs`. Use **Open local workspace** on the local sign-in page. No sponsor key is sent to the browser.

For a fresh clone (Windows Python launcher shown):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test,production,notebook,documents]"
cd frontend
npm ci
cd ..
.\.venv\Scripts\python.exe scripts\setup.py
.\.venv\Scripts\python.exe scripts\start.py
```

On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python`. Run from that machine's actual project folder; the connected D: filesystem is Windows, not a MacBook drive. Install CPU `ffmpeg` and `ffprobe`, or set `NEUROLOOP_FFMPEG` and `NEUROLOOP_FFPROBE` to their executable paths. Setup does not change system PATH or stop existing applications. A hosted notebook cannot reach `127.0.0.1` on your laptop: deploy the CPU API on an approved HTTPS host before connecting remote compute.

## Connect the one notebook

Open `notebooks/NeuroLab.py` in marimo:

```text
python -m marimo edit notebooks/NeuroLab.py
```

Use your notebook provider's secret store for `NEUROLOOP_PUBLIC_API_URL`, `NEUROLOOP_WORKER_TOKEN`, `WANDB_API_KEY`, `WANDB_PROJECT`, `TYPESAFE_API_KEY` and the exact available `NEUROLOOP_INFERENCE_MODEL`. Register your **actual** video, image, vision, TSAM and TRIBE callables in the same registry cell, then press **Start shared worker**. The application writes durable jobs; this notebook initiates authenticated outbound requests, runs each job, uploads immutable results and acknowledges completion. There is no inbound notebook web service.

`docs/NOTEBOOK_INTEGRATION.md` contains the exact callable contracts, media transfer, offloading and result requirements. Missing adapters stay unconfigured. TypeSafe's client uses its verified `/v1/systemone` contract; it is not a guessed API or tokenizer integration.

## Verification

```text
python -m pytest -q
python -m marimo check notebooks/NeuroLab.py
cd frontend
npm run typecheck
npm run build
```

Production uses PostgreSQL plus S3-compatible storage. Run `alembic upgrade head` before startup and turn off development auto-migration. See `docs/PRODUCTION.md`; do not describe local SQLite tests as PostgreSQL/cloud verification.

## Workflows

Create a campaign → upload/select references → set bounded search → start optimization → inspect generation, evidence, TypeSafe decision and branches → give feedback → review selected creative → draft/approve/queue a PAUSED Meta experiment → retrieve actual reports → inspect the intervention ledger in Learning/NeuroLab and submit a sourced research proposal.

A stochastic regeneration is a **variant-level comparison**, not proof that one isolated change caused a business outcome. The cortical view is **Predicted Average Cortical Response**, not a viewer brain scan. No in-app action activates ad delivery or increases spend.
