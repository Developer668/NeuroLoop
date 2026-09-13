"""Single shared NeuroLoop model runtime and research notebook.

No checkpoint downloads or model calls happen merely by opening this notebook.
Install the project first: pip install -e '.[notebook,production,documents]'.
"""

import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full", app_title="NeuroLab • NeuroLoop")


@app.cell
def _():
    import os
    import json
    from pathlib import Path
    import httpx
    import marimo as mo
    from neuroloop_app.config import Settings
    from neuroloop_app.notebook import ModelRegistry, NotebookWorker, GeneratedFile, EvaluationOutput, write_cortical_artifact
    from neuroloop_app.domain import ModelProvenance, EvaluationResult, Score, ConstraintResult
    from neuroloop_app.model_adapters import configure_models

    return ModelRegistry, NotebookWorker, Settings, configure_models, httpx, mo, os


@app.cell
def _(mo):
    mo.md("""
    # NeuroLab
    **One notebook. Real models. A durable, evidence-driven loop.**

    The app owns campaigns, immutable media, job leases, lineage and human gates.
    This notebook owns **all video/image generation, vision, TSAM, TRIBE,
    W&B reasoning and TypeSafe calls**. Configure secrets through your notebook
    provider's secret store, never in a public cell or repository.

    The built-in adapters connect MiniMax H3 FP8, Ideogram 4 FP8, W&B vision,
    and the preserved TSAM/TRIBE evaluators. Enable them through the settings
    in `docs/SELF_HOSTED_NOTEBOOK.md`. Missing models remain `NOT_CONFIGURED`.
    Confirm provider
    permission before using hosted notebook compute for this workload.
    """)
    return


@app.cell
def _(ModelRegistry, Settings, configure_models):
    notebook_settings = Settings()
    registry = configure_models(ModelRegistry(), notebook_settings)
    return notebook_settings, registry


@app.cell
def _(NotebookWorker, notebook_settings, registry):
    worker = NotebookWorker(registry, notebook_settings, worker_id="neurolab-shared")
    return (worker,)


@app.cell
def _(mo):
    start_button = mo.ui.run_button(label="Start shared worker")
    stop_button = mo.ui.run_button(label="Request worker cancellation")
    refresh_button = mo.ui.run_button(label="Refresh real status / research")
    mo.hstack([start_button, stop_button, refresh_button], justify="start")
    return refresh_button, start_button, stop_button


@app.cell
def _(mo, start_button, worker):
    mo.stop(not start_button.value)
    _status = worker.start()
    mo.md(f"Worker request: **{_status['state']}**. Inspect status below.")
    return


@app.cell
def _(mo, stop_button, worker):
    mo.stop(not stop_button.value)
    _status = worker.stop()
    mo.md(f"**{_status['state']}** — {_status['detail']}")
    return


@app.cell
def _(mo, refresh_button, worker):
    refresh_button.value
    mo.vstack([mo.md("## Actual runtime status"), mo.json(worker.last_status), mo.json(worker.capabilities()),
               mo.md("Configured callables are not execution receipts. Model outputs appear only after actual jobs complete.")])
    return


@app.cell
def _(mo):
    run_id_input = mo.ui.text(label="Campaign run ID for research", placeholder="Paste a real run UUID")
    run_id_input
    return (run_id_input,)


@app.cell
def _(httpx, mo, notebook_settings, os, refresh_button, run_id_input):
    refresh_button.value
    _research_token = os.environ.get("NEUROLOOP_RESEARCH_TOKEN", "")
    mo.stop(not _research_token, mo.md("Research reads require `NEUROLOOP_RESEARCH_TOKEN` (a restricted agent token). The worker key cannot authorize human approval or read the dashboard."))
    mo.stop(not run_id_input.value, mo.md("Choose a real run to inspect lineage, evidence, failures and costs."))
    from uuid import UUID
    _run_id = str(UUID(run_id_input.value))
    with httpx.Client(base_url=notebook_settings.public_api_url, headers={"Authorization": "Bearer "+_research_token}, timeout=30) as _client:
        _response = _client.get(f"/api/v2/runs/{_run_id}/export")
        _response.raise_for_status()
        research_data = _response.json()
    return (research_data,)


@app.cell
def _(mo, research_data):
    mo.md("## Reproducible campaign evidence\nRaw observations below retain provenance and missing data. TSAM and TRIBE are proxies, not measured viewer emotions or commercial outcomes.")
    _rows = [{"id": c["id"], "parent": c["parent_id"], "round": c["round"], "status": c["status"], "strategy": c["plan"]["strategy"], "quality_proxy": (c.get("evidence") or {}).get("quality")} for c in research_data.get("creatives", [])]
    mo.vstack([mo.md("### Immutable candidate lineage"), mo.ui.table(_rows, selection=None) if _rows else mo.md("No candidates yet."),
               mo.md("### Actual run budgets / costs"), mo.json(research_data.get("run",{}).get("stats",{})),
               mo.md("### Complete evidence and experiment receipts"), mo.json(research_data)])
    return


if __name__ == "__main__":
    app.run()
