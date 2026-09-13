"""Durable Weave Service API delivery with real trace/parent IDs and readback.

Network calls run outside database transactions. Stable IDs allow reconciliation
rather than duplicate logical traces after a crash. Only metadata is exported.
"""
from __future__ import annotations
import httpx
from sqlalchemy import select
from .db import Store, Trace, record
from .domain import now, utc
from .outcome_telemetry import trace_summary


class WeaveExporter:
    base_url = "https://trace.wandb.ai"

    def __init__(self, store: Store, client=None):
        self.store = store
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)

    def _post(self, path, body):
        key = self.store.settings.wandb_api_key.get_secret_value()
        response = self.client.post(self.base_url + path, auth=("api", key), json=body)
        if path == "/call/read" and response.status_code == 404:
            return {"call": None}
        response.raise_for_status()
        return response.json()

    def drain(self, limit=6):
        settings = self.store.settings
        if not settings.weave_enabled or not settings.wandb_api_key.get_secret_value() or not settings.wandb_project:
            return {"status": "NOT_CONFIGURED", "delivered": 0}
        delivered = 0
        for _ in range(limit):
            with self.store.transaction() as session:
                row = session.scalar(select(Trace).where(Trace.delivered_revision < Trace.revision,
                                     Trace.attempts < 8, Trace.next_attempt <= now()).order_by(Trace.started_at).with_for_update(skip_locked=True).limit(1))
                if row is None:
                    break
                if row.parent_id:
                    parent = session.get(Trace, row.parent_id)
                    if parent and parent.delivered_revision == 0:
                        row.next_attempt = now() + 5
                        continue
                row.attempts += 1
                row.next_attempt = now() + min(3600, 5 * 2 ** row.attempts)
                data = record(row)
            try:
                project = settings.wandb_project
                remote = self._post("/call/read", {"project_id": project, "id": data["id"]}).get("call")
                if remote is None:
                    self._post("/call/start", {"start": {"project_id": project, "id": data["id"],
                               "trace_id": data["run_id"], "parent_id": data["parent_id"], "op_name": data["name"],
                               "started_at": utc(data["started_at"]), "inputs": data["inputs"],
                               "attributes": {"application": "NeuroLoop", "data_policy": "metadata-only", "run_id": data["run_id"]}}})
                if data["ended_at"] is not None:
                    self._post("/call/end", {"end": {"project_id": project, "id": data["id"], "trace_id": data["run_id"],
                               "started_at": utc(data["started_at"]), "ended_at": utc(data["ended_at"]),
                               "exception": data["exception"], "output": data["output"], "summary": trace_summary(data)}})
                receipt = self._post("/call/read", {"project_id": project, "id": data["id"]}).get("call")
                if not receipt or receipt.get("id") != data["id"] or receipt.get("trace_id") != data["run_id"] or receipt.get("parent_id") != data["parent_id"]:
                    raise ValueError("Weave readback did not confirm the trace hierarchy")
                if data["ended_at"] is not None and not receipt.get("ended_at"):
                    raise ValueError("Weave readback did not confirm completion")
                if data["exception"] and not receipt.get("exception"):
                    raise ValueError("Weave did not preserve failure status")
                with self.store.transaction() as session:
                    row = session.get(Trace, data["id"])
                    row.delivered_revision = max(row.delivered_revision, data["revision"])
                    row.status = "DELIVERED" if row.delivered_revision == row.revision else "PENDING"
                    row.url = f"https://wandb.ai/{project}/weave/calls/{data['id']}"
                    row.error = None
                    row.attempts = 0
                delivered += 1
            except Exception as exc:
                with self.store.transaction() as session:
                    row = session.get(Trace, data["id"])
                    row.status = "FAILED" if row.attempts >= 8 else "RETRY"
                    row.error = type(exc).__name__  # Never leak a key or request payload.
        return {"status": "PROCESSED", "delivered": delivered}
