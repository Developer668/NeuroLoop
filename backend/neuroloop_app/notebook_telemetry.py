"""Optional Weave SDK spans for real notebook work; never records model inputs."""
from contextlib import contextmanager
from pathlib import Path
import json
import logging
import os
import threading
import time

_client = None
_lock = threading.Lock()
_log = logging.getLogger(__name__)


def initialize(settings):
    global _client
    if not settings.weave_enabled:
        return None
    with _lock:
        if _client is not None:
            return _client
        try:
            import weave
            if not settings.wandb_project or not settings.wandb_api_key.get_secret_value():
                raise ValueError("Weave project and credential are required")
            os.environ.setdefault("WANDB_API_KEY", settings.wandb_api_key.get_secret_value())
            _client = weave.init(settings.wandb_project, settings={
                "capture_code": False, "implicitly_patch_integrations": False,
                "capture_client_info": False, "capture_system_info": False,
                "print_call_link": False, "enable_disk_fallback": True,
            })
            return _client
        except Exception as exc:
            _log.warning("Weave notebook initialization unavailable: %s", type(exc).__name__)
            return None


@contextmanager
def operation(name, metadata):
    """Metadata must be IDs, stage names, hashes or numeric measurements, not prompts."""
    result, call = {}, None
    started = time.monotonic()
    if _client is not None:
        try:
            call = _client.create_call("neuroloop.notebook." + name, inputs=metadata,
                attributes={"application": "NeuroLoop", "data_policy": "metadata-only", "execution_source": "notebook"})
        except Exception as exc:
            _log.warning("Weave call start unavailable: %s", type(exc).__name__)
    failure = None
    try:
        yield result
    except BaseException as exc:
        failure = RuntimeError(type(exc).__name__)
        result["error_code"] = str(getattr(exc, "code", type(exc).__name__))
        raise
    finally:
        result.update(status="FAILED" if failure else "SUCCEEDED", wall_seconds=time.monotonic() - started)
        if call is not None:
            try:
                call.summary["neuroloop"] = {k: v for k, v in result.items() if isinstance(v, (int, float, bool))}
                _client.finish_call(call, output=result, exception=failure)
            except Exception as exc:
                _log.warning("Weave call finish unavailable: %s", type(exc).__name__)


def publish_snapshot(settings, data, output_dir):
    """Publish a current observation of historical records, not invented execution spans."""
    client = initialize(settings)
    if client is None:
        raise RuntimeError("Weave SDK is not connected")
    import weave
    from .domain import digest
    from .outcome_telemetry import TABLE_NAMES
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    canonical = {k: v for k, v in data.items() if k not in ("generated_at", "snapshot_sha256")}
    if digest(canonical) != data["snapshot_sha256"]:
        raise ValueError("Telemetry snapshot checksum mismatch")
    references = {}
    call = client.create_call("neuroloop.telemetry_snapshot", inputs={"snapshot_sha256": data["snapshot_sha256"],
        "schema_version": data["schema_version"]}, attributes={"data_policy": "metadata-only", "source": "persisted-records"})
    try:
        for table in TABLE_NAMES:
            rows = data[table]
            if rows:
                ref = weave.publish(weave.Dataset(rows=rows), name="neuroloop-outcome-" + table.replace("_", "-"))
                references[table] = ref.uri()
        call.summary["neuroloop"] = {k: v for k, v in data["metrics"].items() if isinstance(v, (int, float, bool))}
        client.finish_call(call, output={"metrics": data["metrics"], "tables": references, "notes": data["notes"]})
        client.flush()
        remote = client.get_call(call.id)
        if not remote.ended_at:
            raise RuntimeError("Weave did not confirm snapshot completion")
        receipt = {"status": "VERIFIED", "snapshot_sha256": data["snapshot_sha256"], "call_id": call.id,
            "url": f"https://wandb.ai/{settings.wandb_project}/weave/calls/{call.id}", "tables": references}
        (root / "weave-snapshot-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt
    except Exception as exc:
        if not call.ended_at:
            client.finish_call(call, exception=RuntimeError(type(exc).__name__))
        client.flush()
        raise
