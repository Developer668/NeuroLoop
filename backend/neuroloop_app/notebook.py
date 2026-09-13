"""One notebook owns every real model, with serialized jobs and durable receipts.

This module does not download models or guess vendor-specific inference functions.
Register your actual H3/image/TRIBE/TSAM callables in the same notebook. Unregistered
models remain NOT_CONFIGURED. Test doubles belong exclusively under tests/.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any, Literal
from urllib.parse import urlparse
from uuid import UUID
import hashlib
import json
import mimetypes
import os
import threading
import time
import httpx
from filelock import FileLock
from .config import Settings
from .domain import EvaluationResult, GenerationResult, ModelProvenance, WorkerHello, digest
from .sponsors import ProviderFailure, TypeSafeKernel, WandBReasoner


class ModelCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalAsset:
    asset_id: str
    path: Path
    kind: str
    mime: str
    sha256: str
    details: dict


@dataclass
class GenerationContext:
    job_id: str
    creative_id: str
    campaign: dict
    prompt: str
    edit_intent: dict
    parameters: dict
    references: list[LocalAsset]
    current_media: LocalAsset | None
    output_dir: Path
    cancelled: Callable[[], bool]
    remaining_gpu_seconds: float
    conditioning: str = "media"

    def check_cancelled(self):
        if self.cancelled():
            raise ModelCancelled("Generation cancellation requested")


@dataclass
class EvaluationContext:
    job_id: str
    creative_id: str
    campaign: dict
    asset: LocalAsset
    references: list[LocalAsset]
    required_constraints: list[str]
    output_dir: Path
    cancelled: Callable[[], bool]

    def check_cancelled(self):
        if self.cancelled():
            raise ModelCancelled("Evaluation cancellation requested")


@dataclass
class GeneratedFile:
    path: Path
    parameters: dict = field(default_factory=dict)
    cost_usd: float | None = None


@dataclass
class EvaluationOutput:
    result: EvaluationResult
    artifacts: list[Path] = field(default_factory=list)


@dataclass
class RegisteredModel:
    provenance: ModelProvenance
    loader: Callable[[], Callable]
    supports_regeneration: bool = False
    park: Callable[[], None] | None = None
    activate: Callable[[], None] | None = None
    cost_ceiling_usd: float | None = None
    callable: Callable | None = None
    supports_media_references: bool = True


class ModelRegistry:
    """Load once; optionally park/resume between models to fit a shared GPU.

    Registration is an integration contract, NOT proof that a checkpoint fits or
    that its predictions are validated. Only completed jobs establish execution.
    """
    def __init__(self):
        self.models: dict[str, RegisteredModel] = {}
        self.active: str | None = None
        self.lock = threading.RLock()

    def register_generator(self, kind: Literal["video", "image"], *, provenance: ModelProvenance,
                           loader: Callable[[], Callable[[GenerationContext], GeneratedFile]],
                           supports_regeneration=True, park=None, activate=None, cost_ceiling_usd=None, supports_media_references=True):
        if kind not in {"video", "image"}:
            raise ValueError("Generator kind must be video or image")
        self.models[f"generate_{kind}"] = RegisteredModel(provenance, loader, supports_regeneration, park, activate, cost_ceiling_usd)
        self.models[f"generate_{kind}"].supports_media_references = supports_media_references

    def register_evaluator(self, name: Literal["vision", "tsam", "tribe"], *, provenance: ModelProvenance,
                           loader: Callable[[], Callable[[EvaluationContext], EvaluationOutput]],
                           park=None, activate=None, cost_ceiling_usd=None):
        if name not in {"vision", "tsam", "tribe"}:
            raise ValueError("Unsupported evaluator")
        self.models[f"evaluate_{name}"] = RegisteredModel(provenance, loader, False, park, activate, cost_ceiling_usd)

    def describe(self):
        result = {}
        for name in ["generate_video", "generate_image", "evaluate_vision", "evaluate_tsam", "evaluate_tribe"]:
            registered = self.models.get(name)
            result[name] = {"status": "READY" if registered else "NOT_CONFIGURED",
                            "detail": "Real callable registered; execution still requires a successful job" if registered else "Register the actual model in this notebook"}
            if registered:
                result[name].update(provenance=registered.provenance.model_dump(), supports_regeneration=registered.supports_regeneration,
                                    supports_media_references=registered.supports_media_references,
                                    cost_ceiling_usd=registered.cost_ceiling_usd, loaded=registered.callable is not None)
        return result

    def invoke(self, capability, context):
        with self.lock:
            entry = self.models.get(capability)
            if entry is None:
                raise ProviderFailure("NOT_CONFIGURED", f"No actual model registered for {capability}")
            if isinstance(context, GenerationContext) and context.current_media and context.conditioning != "text_alternative" and not entry.supports_regeneration:
                raise ProviderFailure("UNAVAILABLE", "This model adapter does not support current-media regeneration")
            if self.active and self.active != capability:
                old = self.models[self.active]
                if old.park:
                    old.park()
            if entry.callable is None:
                from .notebook_telemetry import operation
                with operation("model_load", {"capability": capability, "model": entry.provenance.model}):
                    entry.callable = entry.loader()
                if not callable(entry.callable):
                    raise ProviderFailure("NOT_CONFIGURED", "Model loader did not return a real callable")
            if entry.activate and self.active != capability:
                entry.activate()
            self.active = capability
            context.check_cancelled()
            from .notebook_telemetry import operation
            with operation("model_inference", {"capability": capability, "model": entry.provenance.model}):
                output = entry.callable(context)
            context.check_cancelled()
            return output, entry.provenance

    def park_all(self):
        """Release owned model memory after stop/idle, serialized with inference."""
        with self.lock:
            for entry in self.models.values():
                if entry.callable is not None and entry.park:
                    entry.park()
            self.active = None


def write_cortical_artifact(path: Path, values, times):
    """Write actual model outputs. No synthetic arrays or implicit spatial mapping."""
    import numpy as np
    array, axis = np.asarray(values), np.asarray(times)
    if array.ndim != 2 or array.shape[1] != 20484 or axis.shape != (array.shape[0],):
        raise ValueError("TRIBE adapter must provide real fsaverage5 frames x 20484 values and timestamps")
    if not np.isfinite(array).all() or not np.isfinite(axis).all():
        raise ValueError("Nonfinite neural output")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        np.savez_compressed(stream, values=array.astype("float32"), times=axis.astype("float64"))
    return path


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class NotebookWorker:
    def __init__(self, registry: ModelRegistry, settings: Settings | None = None, *, api_url: str | None = None,
                 worker_id: str = "shared-notebook", cache_dir: Path | str = "notebook-cache", client=None):
        self.settings = settings or Settings()
        self.registry, self.worker_id = registry, worker_id
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        url = api_url or self.settings.public_api_url
        parsed = urlparse(url)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1", "testserver"}):
            raise ValueError("A remote notebook must use an HTTPS application API")
        if parsed.username or parsed.password:
            raise ValueError("Do not put credentials in API URLs")
        self.client = client or httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": "Bearer " + self.settings.worker_token.get_secret_value()}, timeout=60, follow_redirects=False)
        self.reasoner = WandBReasoner(self.settings)
        self.kernel = TypeSafeKernel(self.settings)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.last_status = {"state": "STOPPED"}
        self._execution_lock = FileLock(str(self.cache_dir / "shared-runtime.lock"))

    def capabilities(self):
        capabilities = self.registry.describe()
        capabilities["summary"] = {"status": "READY" if self.settings.wandb_api_key.get_secret_value() and self.settings.inference_model else "NOT_CONFIGURED",
                                   "model": self.settings.inference_model, "cost_ceiling_usd": self.settings.reasoner_cost_ceiling_usd}
        capabilities["reasoner"] = {"status": "READY" if self.settings.wandb_api_key.get_secret_value() and self.settings.inference_model else "NOT_CONFIGURED",
                                    "model": self.settings.inference_model, "detail": "W&B Inference; configured is not execution-verified", "cost_ceiling_usd": self.settings.reasoner_cost_ceiling_usd}
        capabilities["typesafe"] = {"status": "READY" if self.settings.typesafe_api_key.get_secret_value() else "NOT_CONFIGURED",
                                    "model": self.settings.typesafe_model, "detail": "TypeSafe System One; configured is not execution-verified", "cost_ceiling_usd": self.settings.typesafe_cost_ceiling_usd}
        return capabilities

    def register(self):
        hello = WorkerHello(worker_id=self.worker_id, capabilities=self.capabilities(), provider=self.settings.provider,
                            provider_workload_approved=self.settings.provider_workload_approved)
        return self._post("/api/v2/workers/register", hello.model_dump())

    def _post(self, path, body):
        response = self.client.post(path, json=body)
        response.raise_for_status()
        return response.json()

    def _lease(self, job):
        return {"worker_id": self.worker_id, "lease_token": job["lease_token"]}

    def _download(self, metadata):
        identity = str(UUID(metadata["asset_id"]))
        sha = metadata["sha256"]
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ProviderFailure("INVALID_OUTPUT", "Invalid asset digest")
        ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4", "video/webm": ".webm", "audio/wav": ".wav", "text/plain": ".txt", "application/pdf": ".pdf"}.get(metadata["mime"], ".bin")
        target = self.cache_dir / "assets" / identity / (sha + ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
            return LocalAsset(identity, target, metadata["kind"], metadata["mime"], sha, metadata.get("details", {}))
        temp = target.with_suffix(".partial")
        size, hasher = 0, hashlib.sha256()
        try:
            # Construct our own route. Ignore any worker-supplied arbitrary URL/path.
            with self.client.stream("GET", f"/api/v2/assets/{identity}/content") as response:
                response.raise_for_status()
                with temp.open("wb") as stream:
                    for chunk in response.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > self.settings.max_upload_bytes or size > metadata["size"]:
                            raise ProviderFailure("INVALID_OUTPUT", "Asset size exceeds its immutable manifest")
                        stream.write(chunk)
                        hasher.update(chunk)
            if size != metadata["size"] or hasher.hexdigest() != sha:
                raise ProviderFailure("INVALID_OUTPUT", "Asset failed SHA-256 verification")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return LocalAsset(identity, target, metadata["kind"], metadata["mime"], sha, metadata.get("details", {}))

    def _upload(self, job, path, upload_key, output_dir):
        path = Path(path).resolve()
        if not path.is_file() or not path.is_relative_to(output_dir.resolve()):
            raise ProviderFailure("INVALID_OUTPUT", "Model output must be a file inside this job's output directory")
        if path.stat().st_size > self.settings.max_upload_bytes:
            raise ProviderFailure("INVALID_OUTPUT", "Model output exceeds upload budget")
        with path.open("rb") as stream:
            response = self.client.post(f"/api/v2/jobs/{job['id']}/assets", data={**self._lease(job), "upload_key": upload_key},
                                        files={"file": (path.name, stream, "application/octet-stream")})
        response.raise_for_status()
        return response.json()["id"]

    def reconcile(self):
        """Resubmit completed receipts, never rerun a model after an uncertain POST."""
        reconciled = 0
        for file in sorted((self.cache_dir / "jobs").glob("*/result.json"))[-100:]:
            delivery = file.with_name("delivered.json")
            if delivery.exists():
                continue
            lease = file.with_name("lease.json")
            if not lease.exists():
                continue
            job = json.loads(lease.read_text())
            try:
                result = json.loads(file.read_text())
                self._post(f"/api/v2/jobs/{job['id']}/complete", {**self._lease(job), "result": result})
                atomic_json(delivery, {"delivered": True})
                reconciled += 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {403, 404, 409}:
                    atomic_json(file.with_name("reconciliation-error.json"), {"status_code": exc.response.status_code, "detail": "Stale/cancelled lease; preserved result requires human reconciliation"})
                    continue
                raise
        return reconciled

    def run_once(self):
        with self._execution_lock:
            self.register()
            self.reconcile()
            job = self._post(f"/api/v2/workers/{self.worker_id}/claim", {})["job"]
            if job is None:
                self.last_status = {"state": "IDLE", "detail": "No eligible queued job; inspect configured capabilities"}
                return False
            folder = self.cache_dir / "jobs" / str(UUID(job["id"]))
            output_dir = folder / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(folder / "lease.json", job)
            self.last_status = {"state": "RUNNING", "job_id": job["id"], "kind": job["kind"]}
            cancelled, finished = threading.Event(), threading.Event()
            started = time.monotonic()
            deadline = min(job["remaining_wall_seconds"], job["remaining_gpu_seconds"]) if job["kind"] in {"GENERATE", "EVALUATE"} else job["remaining_wall_seconds"]
            def should_cancel():
                return self.stop_event.is_set() or cancelled.is_set() or time.monotonic() - started > deadline
            def pulse():
                interval = max(1, min(15, self.settings.lease_seconds / 3))
                failures = 0
                while not finished.wait(interval):
                    if should_cancel():
                        cancelled.set()
                        break
                    try:
                        entry = self.registry.models.get(job["capability"])
                        model_progress = getattr(entry.callable, "progress", {}) if entry else {}
                        model_phase = model_progress.get("phase") if isinstance(model_progress, dict) else None
                        state = self._post(f"/api/v2/jobs/{job['id']}/heartbeat", {**self._lease(job), "progress": {
                            "message": model_phase or f"{job['capability']} executing in notebook; elapsed {int(time.monotonic() - started)}s",
                            "elapsed_seconds": round(time.monotonic() - started, 1), "phase": job["kind"],
                        }})
                        failures = 0
                        if state.get("cancelled"):
                            cancelled.set()
                            break
                    except httpx.HTTPError:
                        failures += 1
                        if failures >= 2:
                            cancelled.set()
                            break
            heartbeat = threading.Thread(target=pulse, daemon=True, name="neuroloop-heartbeat")
            heartbeat.start()
            try:
                cached = folder / "result.json"
                if cached.exists():
                    result = json.loads(cached.read_text())
                else:
                    from .notebook_telemetry import initialize, operation
                    initialize(self.settings)
                    with operation("job_execution", {"job_id": job["id"], "run_id": job["run_id"], "kind": job["kind"], "attempt": job.get("attempt")}) as telemetry:
                        result = self._execute(job, output_dir, should_cancel)
                        telemetry["model"] = result.get("model") or result.get("provenance", {}).get("model")
                atomic_json(cached, result)  # Persist BEFORE acknowledgement.
                self._post(f"/api/v2/jobs/{job['id']}/complete", {**self._lease(job), "result": result})
                atomic_json(folder / "delivered.json", {"delivered": True})
                self.last_status = {"state": "SUCCEEDED", "job_id": job["id"]}
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {400, 422}:
                    cached = folder / "result.json"
                    if cached.exists():
                        os.replace(cached, folder / f"rejected-result-{time.time_ns()}.json")
                    self._post(f"/api/v2/jobs/{job['id']}/fail", {**self._lease(job), "code": "INVALID_OUTPUT",
                        "detail": "Server rejected the typed result; invalid receipt preserved locally",
                        "safe_to_retry": job["kind"] in {"PLAN", "REVIEW_PLAN", "DECIDE"}})
                    self.last_status = {"state": "INVALID_OUTPUT", "job_id": job["id"]}
                else:
                    self.last_status = {"state": "UNAVAILABLE", "job_id": job["id"], "detail": "HTTP response requires receipt reconciliation"}
                    raise
            except httpx.HTTPError:
                # A response may have been lost AFTER the server committed. Keep
                # the receipt for reconciliation, never blindly regenerate.
                self.last_status = {"state": "UNAVAILABLE", "job_id": job["id"], "detail": "Transport failed; local receipt and media preserved"}
                raise
            except Exception as exc:
                if isinstance(exc, ProviderFailure):
                    code, detail, retry = exc.code, exc.detail, exc.safe_to_retry
                elif isinstance(exc, ModelCancelled):
                    code, detail, retry = "CANCELLED", "Model cancellation requested; partial files remain in notebook journal", False
                elif "outofmemory" in type(exc).__name__.lower() or "out of memory" in str(exc).lower():
                    code, detail, retry = "OUT_OF_MEMORY", "Model ran out of memory. Configure explicit offload/park hooks or a validated safe profile", False
                else:
                    code, detail, retry = "INVALID_OUTPUT", f"Model/contract failed with {type(exc).__name__}; no substitute result emitted", False
                receipt = {"code": code, "detail": detail, "safe_to_retry": retry,
                           "gpu_seconds": time.monotonic() - started if job["kind"] in {"GENERATE", "EVALUATE"} else 0}
                atomic_json(folder / "failure.json", receipt)
                self._post(f"/api/v2/jobs/{job['id']}/fail", {**self._lease(job), **receipt})
                self.last_status = {"state": code, "job_id": job["id"], "detail": detail}
            finally:
                finished.set()
                heartbeat.join(timeout=2)
            return True

    def _execute(self, job, output_dir, cancelled):
        payload = job["payload"]
        if job["kind"] == "SUMMARY":
            self.reasoner.last_summary_receipt = None
            try:
                return self.reasoner.summarize(payload["evidence"], payload["execution"])
            finally:
                receipt = getattr(self.reasoner, "last_summary_receipt", None)
                if receipt:
                    atomic_json(output_dir / "summary-provider-receipt.json", receipt)
        if job["kind"] == "PLAN":
            from .vision_adapter import VisionAdapter
            from types import SimpleNamespace
            vision = VisionAdapter(self.settings.model_copy(update={"vision_model": self.settings.inference_model}))
            media = []
            assets = payload.get("references", []) + [p["asset"] for p in payload.get("parents", [])]
            seen = set()
            for metadata in assets:
                if metadata["asset_id"] in seen:
                    continue
                seen.add(metadata["asset_id"])
                if metadata["kind"] in {"image", "video"}:
                    media.extend(vision.media_content(self._download(metadata), SimpleNamespace(check_cancelled=lambda: self._check_plan_cancelled(cancelled)), count=6))
            self.reasoner.last_plan_receipt = None
            try:
                return self.reasoner.plan(payload, media_content=media).model_dump()
            finally:
                receipt = getattr(self.reasoner, "last_plan_receipt", None)
                if receipt:
                    atomic_json(output_dir / "plan-provider-receipt.json", receipt)
        if job["kind"] == "REVIEW_PLAN":
            return self.kernel.review_plan(payload).model_dump()
        if job["kind"] == "DECIDE":
            return self.kernel.decide(payload).model_dump()
        refs = [self._download(a) for a in payload.get("references", [])]
        started = time.monotonic()
        if job["kind"] == "GENERATE":
            current = next((a for a in refs if a.asset_id == payload.get("current_creative_asset_id")), None)
            if payload["plan"]["parent_creative_id"] and current is None:
                raise ProviderFailure("INVALID_OUTPUT", "Regeneration requires the actual parent media")
            context = GenerationContext(job["id"], payload["creative_id"], payload["campaign"], payload["plan"]["prompt"],
                        payload["plan"]["edit_intent"], {**payload["plan"]["parameters"], "seed": payload["plan"].get("seed") if payload["plan"].get("seed") is not None else 11}, refs, current, output_dir, cancelled, job["remaining_gpu_seconds"], conditioning=payload.get("conditioning", "media"))
            journal = output_dir.parent / "generated.json"
            if journal.exists():
                old = json.loads(journal.read_text())
                if old["request_hash"] != digest(payload):
                    raise ProviderFailure("INVALID_OUTPUT", "Cached generation does not match the immutable request")
                generated = GeneratedFile(Path(old["path"]), old["parameters"], old["cost_usd"])
                provenance = ModelProvenance.model_validate(old["provenance"])
                elapsed = old["elapsed"]
            else:
                generated, provenance = self.registry.invoke(job["capability"], context)
                if not isinstance(generated, GeneratedFile):
                    raise ProviderFailure("INVALID_OUTPUT", "Generator must return GeneratedFile, not an invented URL or result dictionary")
                elapsed = time.monotonic() - started
                atomic_json(journal, {"request_hash": digest(payload), "path": str(generated.path), "parameters": generated.parameters,
                            "cost_usd": generated.cost_usd, "provenance": provenance.model_dump(), "elapsed": elapsed})
            asset_id = self._upload(job, generated.path, "generated-media", output_dir)
            return GenerationResult(asset_id=asset_id, provenance=provenance, runtime_seconds=elapsed, gpu_seconds=elapsed,
                                    cost_usd=generated.cost_usd, parameters={**generated.parameters, "gpu_budget_measurement": "serialized_model_wall_seconds"}).model_dump()
        if job["kind"] == "EVALUATE":
            asset = self._download(payload["asset"])
            context = EvaluationContext(job["id"], payload["creative_id"], payload["campaign"], asset, refs,
                        payload["required_constraints"], output_dir, cancelled)
            output, provenance = self.registry.invoke(job["capability"], context)
            if not isinstance(output, EvaluationOutput):
                raise ProviderFailure("INVALID_OUTPUT", "Evaluator must return EvaluationOutput with real, provenance-tagged evidence")
            result = output.result
            if result.provenance != provenance:
                raise ProviderFailure("INVALID_OUTPUT", "Returned evaluator provenance differs from the registered checkpoint/configuration")
            artifacts = [self._upload(job, p, f"evaluation-{i}", output_dir) for i, p in enumerate(output.artifacts)]
            result = result.model_copy(update={"artifact_ids": artifacts,
                "gpu_seconds": 0 if payload["evaluator"] == "vision" else time.monotonic() - started})
            return result.model_dump()
        raise ProviderFailure("UNAVAILABLE", "Unsupported job type")

    @staticmethod
    def _check_plan_cancelled(cancelled):
        if cancelled():
            raise ModelCancelled("Planning cancellation requested")

    def start(self):
        if self.thread and self.thread.is_alive():
            return self.last_status
        if self.settings.provider.lower() == "molab" and not self.settings.provider_workload_approved:
            raise RuntimeError("Confirm that this workload is permitted by molab/hackathon staff before starting")
        self.stop_event.clear()
        def loop():
            idle_since = time.monotonic()
            while not self.stop_event.is_set():
                try:
                    worked = self.run_once()
                    if worked:
                        idle_since = time.monotonic()
                    if not worked:
                        if time.monotonic() - idle_since >= self.settings.worker_idle_seconds:
                            self.stop_event.set()
                            self.last_status = {"state": "IDLE_STOPPED", "detail": "Idle timeout reached; model memory released. Stop the host session to stop provider billing."}
                            break
                        self.stop_event.wait(3)
                except Exception as exc:
                    self.last_status = {"state": "UNAVAILABLE", "detail": type(exc).__name__ + ": worker stopped accepting work until connection/configuration recovers"}
                    if time.monotonic() - idle_since >= self.settings.worker_idle_seconds:
                        self.stop_event.set()
                        self.last_status = {"state": "IDLE_STOPPED", "detail": "Connection unavailable through the idle timeout; release host compute when finished."}
                        break
                    self.stop_event.wait(10)
            self.registry.park_all()
        self.thread = threading.Thread(target=loop, daemon=True, name="neuroloop-notebook")
        self.thread.start()
        return {"state": "STARTING"}

    def stop(self):
        self.stop_event.set()
        return {"state": "CANCELLATION_REQUESTED", "detail": "Model callbacks must check context.cancelled; an in-flight GPU kernel cannot be forcibly preempted by this thread"}
