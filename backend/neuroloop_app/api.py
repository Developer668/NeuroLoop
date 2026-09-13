"""FastAPI application. All neural generation/evaluation stays in the notebook."""
from __future__ import annotations
import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Literal
import hashlib
import hmac
import json
import secrets
import tempfile
import time
from urllib.parse import urlencode
from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .config import ROOT, Settings
from .db import ArtifactBackup, Asset, AuthSession, Creative, Deployment, Evaluation, NotebookEvidence, Job, Run, Store, Trace, Worker, record
from .domain import (AdAssetSyncRequest, CampaignSpec, CompleteJob, DeploymentSpec, EvaluationResult, ModelProvenance, FailJob, FeedbackRequest,
                     LeaseRequest, ResearchProposal, ResumeRequest, StartRun, WorkerHello, digest, now, uid)
from .engine import DomainError, LoopEngine, required, emit, close_trace
from .storage import ObjectStore, StorageError, inspect_media
from .telemetry import WeaveExporter
from .meta import MetaClient, MetaService, MetaFailure
from .ad_publish import AdPublishService, AdProviderFailure, PROVIDERS


class Login(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class Approval(BaseModel):
    review_digest: str = Field(min_length=64, max_length=64)
    confirmation: str


class NotebookReport(BaseModel):
    evaluator: Literal["generation", "summary", "inventory"]
    status: Literal["SUCCEEDED", "FAILED"]
    provenance: ModelProvenance
    observations: dict
    scores: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list, max_length=0)


class EvidenceImport(BaseModel):
    input_asset_id: str
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_receipt: str = Field(min_length=1, max_length=300)
    source_kind: Literal["reference_evaluation", "generated_ad_evaluation"]
    title: str = Field(min_length=1, max_length=250)
    result: EvaluationResult | NotebookReport


class TooLarge(Exception):
    pass


class RequestSizeLimit:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        multipart = headers.get(b"content-type", b"").startswith(b"multipart/form-data")
        limit = self.settings.max_upload_bytes + 65536 if multipart else self.settings.max_request_bytes
        count = 0
        async def bounded_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > limit:
                raise TooLarge()
            return message
        try:
            if int(headers.get(b"content-length", b"0")) > limit:
                raise TooLarge()
            await self.app(scope, bounded_receive, send)
        except TooLarge:
            response = JSONResponse({"detail": "Request exceeds the configured size limit"}, status_code=413)
            await response(scope, receive, send)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    store = Store(settings)
    store.initialize()
    objects = ObjectStore(settings)
    engine = LoopEngine(store, objects)
    exporter = WeaveExporter(store)
    from .artifact_backup import ArtifactExporter
    artifact_exporter = ArtifactExporter(store, objects, engine)
    publishing = AdPublishService(store, objects)
    meta = MetaService(store, objects, MetaClient(settings, token_provider=lambda: publishing.server_access_token("meta")))
    rate_windows = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        async def maintain():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(engine.recover_expired)
                    await asyncio.to_thread(exporter.drain)
                except Exception:
                    # Durable state retains errors. Never let telemetry kill the API.
                    import logging
                    logging.getLogger(__name__).exception("Maintenance task failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        async def meta_queue():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(meta.recover_stale)
                    await asyncio.to_thread(meta.drain)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Meta queue failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        async def backup_queue():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(artifact_exporter.drain)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Artifact backup queue failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        tasks = [asyncio.create_task(maintain()), asyncio.create_task(meta_queue()), asyncio.create_task(backup_queue())]
        yield
        stop.set()
        await asyncio.gather(*tasks)

    app = FastAPI(title="NeuroLoop", version="0.2.0", lifespan=lifespan)
    app.state.store, app.state.engine, app.state.objects = store, engine, objects
    app.add_middleware(RequestSizeLimit, settings=settings)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    from pydantic import ValidationError
    @app.exception_handler(ValidationError)
    async def invalid_contract(request, exc):
        return JSONResponse({"detail": "Invalid typed result", "fields": [list(e["loc"]) for e in exc.errors()]}, status_code=422)

    @app.exception_handler(MetaFailure)
    async def meta_failure(request, exc):
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=503)

    @app.exception_handler(AdProviderFailure)
    async def ad_provider_failure(request, exc):
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=503)

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.middleware("http")
    async def guard(request, call_next):
        token = request.headers.get("authorization", "")
        identity = hashlib.sha256((token or (request.client.host if request.client else "unknown")).encode()).hexdigest()
        timestamp = time.monotonic()
        window = rate_windows[identity]
        while window and timestamp - window[0] > 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"})
        window.append(timestamp)
        if len(rate_windows) > 10000:
            for key in list(rate_windows):
                if not rate_windows[key] or timestamp - rate_windows[key][-1] > 60:
                    del rate_windows[key]
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != settings.frontend_origin:
            return JSONResponse({"detail": "Cross-origin write denied"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    def bearer(request):
        header = request.headers.get("authorization", "")
        return header[7:] if header.startswith("Bearer ") else ""

    def role(request: Request):
        token = bearer(request)
        if not token:
            raise HTTPException(401, "Authentication required")
        worker_key = settings.worker_token.get_secret_value()
        if worker_key and hmac.compare_digest(token, worker_key):
            return "worker"
        agent_key = settings.agent_token.get_secret_value()
        if agent_key and hmac.compare_digest(token, agent_key):
            return "operator"
        root_key = settings.operator_token.get_secret_value()
        if root_key and hmac.compare_digest(token, root_key):
            return "operator"
        with store.read() as session:
            row = session.get(AuthSession, hashlib.sha256(token.encode()).hexdigest())
            if row and not row.revoked and row.expires_at > now():
                return row.role
        raise HTTPException(401, "Session is missing, revoked or expired")

    def operator(principal=Depends(role)):
        if principal not in {"operator", "human"}:
            raise HTTPException(403, "Operator permission required")
        return principal

    def human(principal=Depends(role)):
        if principal != "human":
            raise HTTPException(403, "An authenticated human review session is required")
        return principal

    def worker(principal=Depends(role)):
        if principal != "worker":
            raise HTTPException(403, "Notebook worker permission required")
        return principal

    def create_session():
        token = secrets.token_urlsafe(48)
        with store.transaction() as session:
            session.add(AuthSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), role="human", expires_at=now() + settings.session_seconds))
        return {"token": token, "expires_in": settings.session_seconds}

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.2.0", "models_in_api_process": False, "environment": settings.environment}

    @app.get("/api/v2/telemetry", dependencies=[Depends(operator)])
    def outcome_telemetry():
        from .outcome_telemetry import snapshot
        return snapshot(store)

    @app.get("/api/v2/workers/telemetry", dependencies=[Depends(worker)])
    def worker_outcome_telemetry():
        from .outcome_telemetry import snapshot
        return snapshot(store)

    @app.post("/auth/login")
    def login(body: Login):
        key = settings.operator_token.get_secret_value()
        if not key or not hmac.compare_digest(body.token, key):
            raise HTTPException(401, "Operator key not accepted")
        return create_session()

    @app.post("/auth/local")
    def local_login(request: Request, x_neuroloop_bootstrap: str | None = Header(default=None)):
        key = settings.local_bootstrap_token.get_secret_value()
        if settings.environment != "development" or not key or not x_neuroloop_bootstrap or not hmac.compare_digest(key, x_neuroloop_bootstrap):
            raise HTTPException(403, "Local bootstrap is not authorized")
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "Local bootstrap requires a loopback connection")
        return create_session()

    @app.post("/auth/revoke")
    def revoke(request: Request, principal=Depends(role)):
        with store.transaction() as session:
            row = session.get(AuthSession, hashlib.sha256(bearer(request).encode()).hexdigest())
            if row:
                row.revoked = True
        return {"revoked": True}

    @app.get("/api/capabilities", dependencies=[Depends(operator)])
    @app.get("/api/v2/capabilities", dependencies=[Depends(operator)])
    def capabilities():
        with store.read() as session:
            workers = [record(w) for w in session.scalars(select(Worker))]
            for w in workers:
                w["online"] = now() - w["heartbeat_at"] < settings.worker_stale_seconds
            trace_count = session.scalar(select(func.count()).select_from(Trace).where(Trace.delivered_revision > 0))
            queued = session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(["PENDING", "RETRY"])))
            active = session.scalar(select(func.count()).select_from(Job).where(Job.status == "LEASED"))
        return {"application": "NeuroLoop", "version": "0.2.0", "workers": workers, "queue_depth": queued, "active_jobs": active,
                "storage": settings.storage, "database": "sqlite-development" if store.sqlite else "postgresql",
                "weave": {"status": "NOT_CONFIGURED" if not(settings.weave_enabled and settings.wandb_project and settings.wandb_api_key.get_secret_value()) else "VERIFIED_DELIVERY" if trace_count else "CONFIGURED_NOT_VERIFIED", "delivered_traces": trace_count},
                "aria": {"status": "MANUAL_RESEARCH_IMPORT", "detail": "Real history export and typed proposal intake; no undocumented ARIA API is called."},
                "meta": {"status": "CONFIGURED_NOT_VERIFIED" if meta.client.configured() else "NOT_CONFIGURED", "activation": "DISABLED"},
                "publishing": {item["provider"]: {"configured": item["configured"], "connected": item["connected"], "upload_ready": item["upload_ready"]} for item in publishing.statuses()},
                "model_execution": "NOTEBOOK_ONLY", "scientific_label": "Predicted Average Cortical Response"}

    @app.get("/api/v2/campaigns", dependencies=[Depends(operator)])
    def campaigns():
        return engine.campaigns()

    @app.post("/api/v2/campaigns", dependencies=[Depends(operator)], status_code=201)
    def campaign_create(body: CampaignSpec):
        return engine.create_campaign(body)

    @app.get("/api/v2/campaigns/{campaign_id}", dependencies=[Depends(operator)])
    def campaign_detail(campaign_id: str):
        return engine.campaign_detail(campaign_id)

    async def save_upload(campaign_id, file, **kwargs):
        temp = objects.temp / uid()
        try:
            with temp.open("xb") as stream:
                size = 0
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise HTTPException(413, "Upload exceeds maximum size")
                    stream.write(chunk)
            return await asyncio.to_thread(engine.add_asset, campaign_id, temp, file.filename or "asset", **kwargs)
        finally:
            temp.unlink(missing_ok=True)
            await file.close()

    @app.post("/api/v2/campaigns/{campaign_id}/assets", dependencies=[Depends(operator)], status_code=201)
    async def upload(campaign_id: str, file: UploadFile = File(...)):
        return await save_upload(campaign_id, file)

    @app.post("/api/v2/campaigns/{campaign_id}/runs", dependencies=[Depends(operator)], status_code=202)
    def start_run(campaign_id: str, body: StartRun, idempotency_key: str = Header(...)):
        return engine.start(campaign_id, body, idempotency_key)

    @app.get("/api/v2/runs/{run_id}", dependencies=[Depends(operator)])
    def run_snapshot(run_id: str):
        return engine.snapshot(run_id)

    @app.post("/api/v2/runs/{run_id}/cancel", dependencies=[Depends(operator)])
    def cancel(run_id: str):
        return engine.cancel(run_id)

    @app.post("/api/v2/runs/{run_id}/resume", dependencies=[Depends(human)])
    def resume(run_id: str, body: ResumeRequest):
        return engine.resume(run_id, body.acknowledge_uncertain_cost)

    @app.post("/api/v2/runs/{run_id}/summary/retry", dependencies=[Depends(operator)])
    def retry_summary(run_id: str):
        return engine.retry_summary(run_id)

    @app.post("/api/v2/runs/{run_id}/repair", dependencies=[Depends(operator)])
    def retry_constraint_repair(run_id: str):
        return engine.retry_constraint_repair(run_id)

    @app.post("/api/v2/runs/{run_id}/plan/correct", dependencies=[Depends(operator)])
    def correct_invalid_plan(run_id: str):
        return engine.correct_invalid_plan(run_id)

    @app.post("/api/v2/runs/{run_id}/finish", dependencies=[Depends(human)])
    def finish(run_id: str):
        with store.transaction() as session:
            run = required(session, Run, run_id, lock=True)
            if run.state != "READY_FOR_REVIEW":
                raise DomainError("Only a reviewed run can be finalized")
            run.state = "COMPLETE"
            emit(session, run, "REVIEW_COMPLETED", note="Human finalized creative optimization without advertising activation")
            close_trace(session, run.id, {"status": "COMPLETE", "selected_creative_ids": run.selected_ids, "stats": run.stats})
            return record(run)

    @app.get("/api/v2/runs/{run_id}/export", dependencies=[Depends(operator)])
    def export(run_id: str):
        return JSONResponse(engine.snapshot(run_id), headers={"Content-Disposition": f'attachment; filename="neuroloop-{run_id}.json"'})

    @app.post("/api/v2/campaigns/{campaign_id}/feedback", dependencies=[Depends(operator)], status_code=201)
    def feedback(campaign_id: str, body: FeedbackRequest, principal=Depends(operator)):
        return engine.feedback(campaign_id, body, actor=principal)

    @app.get("/api/v2/learning", dependencies=[Depends(operator)])
    def learning():
        return engine.learning()

    @app.post("/api/v2/policies/proposals", dependencies=[Depends(operator)], status_code=201)
    def propose(body: ResearchProposal):
        return engine.propose_policy(body)

    @app.get("/api/v2/workers/research-bundle", dependencies=[Depends(worker)])
    def research_bundle():
        path = settings.research_bundle_path
        if path is None or not path.is_file():
            raise HTTPException(404, "Research bundle is not configured")
        return FileResponse(path, media_type="application/zip", filename="neuroloop-research-runtime.zip",
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/v2/workers/application-runtime", dependencies=[Depends(worker)])
    def application_runtime():
        import zipfile
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(Path(__file__).parent.glob("*.py")):
                archive.write(path, "neuroloop_app/" + path.name)
        return StreamingResponse(iter([buffer.getvalue()]), media_type="application/zip")

    @app.post("/api/v2/workers/evidence", dependencies=[Depends(worker)], status_code=201)
    async def import_evidence(metadata: str = Form(...), cortical: UploadFile | None = File(None)):
        body = EvidenceImport.model_validate_json(metadata)
        if body.result.artifact_ids:
            raise DomainError("Evidence artifacts must be uploaded with their receipt", 422)
        temp = objects.temp / uid()
        try:
            info = None
            if cortical:
                with temp.open("xb") as stream:
                    size = 0
                    while chunk := await cortical.read(1024 * 1024):
                        size += len(chunk)
                        if size > settings.max_upload_bytes:
                            raise HTTPException(413, "Cortical upload exceeds maximum size")
                        stream.write(chunk)
                info = inspect_media(temp, settings, internal=True)
                if info.kind != "cortical" or body.result.evaluator != "tribe":
                    raise DomainError("Expected a validated TRIBE cortical archive", 422)
            if body.result.evaluator == "tribe" and body.result.status == "SUCCEEDED" and info is None:
                raise DomainError("Successful TRIBE receipts require the real cortical artifact", 422)
            with store.transaction() as session:
                source = required(session, Asset, body.input_asset_id)
                if source.sha256 != body.input_sha256:
                    raise DomainError("Receipt does not match the input media checksum", 422)
                parent_id = body.result.observations.get("parent_asset_id") if body.result.evaluator == "generation" else None
                if parent_id:
                    parent = required(session, Asset, parent_id)
                    if parent.campaign_id != source.campaign_id or parent.id == source.id:
                        raise DomainError("Invalid revision parent", 422)
                    citations = body.result.observations.get("based_on_evidence_ids", [])
                    if not isinstance(citations, list) or not citations:
                        raise DomainError("A revision must cite actual parent evidence", 422)
                    for citation in citations:
                        evidence_row = required(session, NotebookEvidence, citation)
                        if evidence_row.input_asset_id != parent.id:
                            raise DomainError("Revision evidence does not evaluate its parent", 422)
                previous = session.scalar(select(NotebookEvidence).where(NotebookEvidence.source_receipt == body.source_receipt))
                request_hash = digest(body.model_dump())
                if previous:
                    if previous.result.get("import_hash") != request_hash:
                        raise DomainError("Receipt identifier already contains different evidence", 409)
                    if info:
                        existing = required(session, Asset, previous.result["artifact_ids"][0])
                        if hashlib.sha256(temp.read_bytes()).hexdigest() != existing.sha256:
                            raise DomainError("Receipt identifier already contains different cortical bytes", 409)
                    return record(previous)
                result = body.result.model_dump()
                result["import_hash"] = request_hash
                if info:
                    identity = uid()
                    key, sha, size = objects.put(temp, source.campaign_id, identity)
                    session.add(Asset(id=identity, campaign_id=source.campaign_id, name="cortical.npz", kind=info.kind, mime=info.mime,
                                      sha256=sha, size=size, object_key=key, details=info.details))
                    result["artifact_ids"] = [identity]
                row = NotebookEvidence(campaign_id=source.campaign_id, input_asset_id=source.id, source_receipt=body.source_receipt,
                    source_kind=body.source_kind, title=body.title, evaluator=body.result.evaluator,
                    comparison_key=body.result.provenance.comparison_key, result=result)
                session.add(row)
                session.flush()
                return record(row)
        finally:
            temp.unlink(missing_ok=True)
            if cortical:
                await cortical.close()

    @app.get("/api/v2/evidence", dependencies=[Depends(operator)])
    def notebook_evidence(campaign_id: str | None = None):
        with store.read() as session:
            query = select(NotebookEvidence).order_by(NotebookEvidence.created_at.desc()).limit(200)
            if campaign_id:
                query = select(NotebookEvidence).where(NotebookEvidence.campaign_id == campaign_id).order_by(NotebookEvidence.created_at.desc()).limit(200)
            imported = [{**record(row), "input_asset": record(required(session, Asset, row.input_asset_id)),
                     "artifacts": [record(required(session, Asset, identity)) for identity in row.result.get("artifact_ids", [])]}
                    for row in session.scalars(query)]
            evaluations = select(Evaluation).join(Creative, Evaluation.creative_id == Creative.id)
            if campaign_id:
                evaluations = evaluations.where(Creative.campaign_id == campaign_id)
            for row in session.scalars(evaluations.order_by(Evaluation.created_at.desc()).limit(200)):
                creative = required(session, Creative, row.creative_id)
                if creative.output_asset_id:
                    imported.append({**record(row), "input_asset_id": creative.output_asset_id,
                        "input_asset": record(required(session, Asset, creative.output_asset_id)),
                        "artifacts": [record(required(session, Asset, identity)) for identity in row.result.get("artifact_ids", [])],
                        "source_kind": "campaign_loop", "source_receipt": row.job_id,
                        "title": f"Round {creative.round} · {row.evaluator.upper()} · {creative.id[:8]}"})
            return sorted(imported, key=lambda row: row["created_at"], reverse=True)

    @app.get("/api/v2/backups", dependencies=[Depends(operator)])
    def backups():
        with store.read() as session:
            return {"enabled": settings.wandb_artifacts_enabled, "project": settings.wandb_project,
                    "items": [record(row) for row in session.scalars(select(ArtifactBackup))]}

    @app.get("/api/v2/workers/evidence-context/{asset_id}", dependencies=[Depends(worker)])
    def evidence_context(asset_id: str, run_id: str | None = None):
        with store.read() as session:
            asset = required(session, Asset, asset_id)
            rows = [record(row) for row in session.scalars(select(NotebookEvidence).where(
                NotebookEvidence.input_asset_id == asset_id, NotebookEvidence.evaluator != "summary"))]
            if run_id and required(session, Run, run_id).campaign_id != asset.campaign_id:
                raise DomainError("Run and media belong to different campaigns", 422)
            return {"asset":record(asset), "evidence":rows, "run":engine.snapshot(run_id) if run_id else None}

    @app.post("/api/v2/workers/evidence-files/{asset_id}", dependencies=[Depends(worker)], status_code=201)
    async def evidence_file(asset_id: str, file: UploadFile = File(...)):
        with store.read() as session:
            source = required(session, Asset, asset_id)
            campaign_id = source.campaign_id
        return await save_upload(campaign_id, file)

    @app.post("/api/v2/workers/register", dependencies=[Depends(worker)])
    def worker_register(body: WorkerHello):
        return engine.register_worker(body)

    @app.post("/api/v2/workers/{worker_id}/claim", dependencies=[Depends(worker)])
    def claim(worker_id: str):
        return {"job": engine.claim(worker_id)}

    @app.post("/api/v2/jobs/{job_id}/heartbeat", dependencies=[Depends(worker)])
    def heartbeat(job_id: str, body: LeaseRequest):
        return engine.heartbeat(job_id, body.worker_id, body.lease_token, body.progress)

    @app.post("/api/v2/jobs/{job_id}/complete", dependencies=[Depends(worker)])
    def complete(job_id: str, body: CompleteJob):
        return engine.complete(job_id, body)

    @app.post("/api/v2/jobs/{job_id}/fail", dependencies=[Depends(worker)])
    def fail(job_id: str, body: FailJob):
        return engine.fail(job_id, body)

    @app.post("/api/v2/jobs/{job_id}/assets", dependencies=[Depends(worker)], status_code=201)
    async def worker_upload(job_id: str, worker_id: str = Form(...), lease_token: str = Form(...), upload_key: str = Form(...), file: UploadFile = File(...)):
        with store.read() as session:
            job = required(session, Job, job_id)
            campaign_id = required(session, Run, job.run_id).campaign_id
        return await save_upload(campaign_id, file, job_id=job_id, worker_id=worker_id, lease_token=lease_token, upload_key=upload_key)

    def signed(asset_id, sha, expiry):
        key = settings.signing_key.get_secret_value()
        if not key:
            raise DomainError("Signed asset URLs are not configured", 503)
        return hmac.new(key.encode(), f"{asset_id}:{sha}:{expiry}".encode(), hashlib.sha256).hexdigest()

    @app.get("/api/v2/assets/{asset_id}/url", dependencies=[Depends(operator)])
    def asset_url(asset_id: str):
        asset = engine.asset(asset_id)
        expiry = int(now()) + 900
        return {"url": settings.public_api_url.rstrip("/") + f"/api/v2/assets/{asset_id}/content?" + urlencode({"expires": expiry, "signature": signed(asset_id, asset["sha256"], expiry)}), "expires_at": expiry}

    @app.get("/api/v2/assets/{asset_id}/content")
    def content(asset_id: str, request: Request, expires: int | None = None, signature: str | None = None):
        asset = engine.asset(asset_id)
        if signature is not None and expires is not None:
            if not now() <= expires <= now() + 901 or not hmac.compare_digest(signature, signed(asset_id, asset["sha256"], expires)):
                raise HTTPException(403, "Expired or invalid asset signature")
        else:
            role(request)
        disposition = "inline" if asset["kind"] in {"video", "image", "audio"} else "attachment"
        headers = {"Content-Security-Policy": "sandbox; default-src 'none'", "ETag": f'"{asset["sha256"]}"'}
        if settings.storage == "local":
            return FileResponse(objects.local_path(asset["object_key"]), media_type=asset["mime"], filename=asset["name"], content_disposition_type=disposition, headers=headers)
        headers.update({"Content-Disposition": disposition, "Content-Length": str(asset["size"])})
        return StreamingResponse(objects.stream(asset["object_key"]), media_type=asset["mime"], headers=headers)

    @app.get("/api/geometry", dependencies=[Depends(operator)])
    def geometry():
        path = ROOT / "frontend" / "public" / "fsaverage5.json"
        if not path.exists():
            raise HTTPException(404, "Verified cortical surface was not installed")
        return FileResponse(path, media_type="application/json")

    @app.get("/api/evaluations/{evaluation_id}/frame", dependencies=[Depends(operator)])
    def cortical_frame(evaluation_id: str, index: int = 0, reference: str | None = None):
        import numpy as np
        def read_frame(session, identity):
            evaluation = session.get(Evaluation, identity) or session.get(NotebookEvidence, identity)
            if evaluation is None:
                raise DomainError("Evaluation not found", 404)
            if evaluation.evaluator != "tribe" or evaluation.result["status"] != "SUCCEEDED":
                raise DomainError("No real TRIBE cortical output for this evaluation", 404)
            candidates = [required(session, Asset, a) for a in evaluation.result.get("artifact_ids", [])]
            asset = next((a for a in candidates if a.kind == "cortical"), None)
            if asset is None:
                raise DomainError("Cortical artifact unavailable", 404)
            with np.load(BytesIO(objects.read(asset.object_key)), allow_pickle=False) as data:
                if not 0 <= index < len(data["values"]):
                    raise DomainError("Cortical frame out of range", 422)
                return evaluation, data["values"][index].copy(), float(data["times"][index]), asset.details["range"]
        with store.read() as session:
            evaluation, values, timestamp, value_range = read_frame(session, evaluation_id)
            if reference:
                other, reference_values, reference_time, _ = read_frame(session, reference)
                if other.comparison_key != evaluation.comparison_key or abs(timestamp-reference_time) > 0.01:
                    raise DomainError("Cannot compare incompatible evaluators or unaligned cortical time points", 422)
                values = values - reference_values
                value_range = [float(values.min()), float(values.max())]
        return {"values": values.tolist(), "range": value_range, "time": timestamp, "label": "Predicted Average Cortical Response"}

    @app.get("/api/evaluations/{evaluation_id}/regions", dependencies=[Depends(operator)])
    def cortical_regions(evaluation_id: str):
        import numpy as np
        path = ROOT / "data" / "geometry" / "atlas.json"
        if not path.is_file():
            raise DomainError("Anatomical atlas is not installed", 404)
        raw = path.read_bytes()
        atlas = json.loads(raw)
        if atlas.get("mesh") != "fsaverage5" or any(len(atlas.get(h, [])) != 10242 for h in ("left", "right")):
            raise DomainError("Anatomical atlas does not match fsaverage5", 422)
        with store.read() as session:
            row = session.get(Evaluation, evaluation_id) or session.get(NotebookEvidence, evaluation_id)
            if row is None or row.evaluator != "tribe" or row.result["status"] != "SUCCEEDED":
                raise DomainError("Successful TRIBE evidence required", 404)
            assets = [required(session, Asset, a) for a in row.result.get("artifact_ids", [])]
            asset = next((a for a in assets if a.kind == "cortical"), None)
            if asset is None:
                raise DomainError("Cortical artifact unavailable", 404)
            with np.load(BytesIO(objects.read(asset.object_key)), allow_pickle=False) as data:
                values, times = data["values"], data["times"].tolist()
            regions = []
            for hemisphere, offset in (("left", 0), ("right", 10242)):
                mapping = np.asarray(atlas[hemisphere])
                for index, label in enumerate(atlas["labels"]):
                    mask = mapping == index
                    if not mask.any() or label.lower() in {"unknown", "medial_wall"}:
                        continue
                    x = values[:, offset:offset+10242][:, mask]
                    regions.append({"id":f"{hemisphere}:{index}","hemisphere":hemisphere,"name":label.replace("_", " "),
                        "vertices":int(mask.sum()),"mean":x.mean(axis=1).tolist(),"rms":float(np.sqrt(np.mean(x**2)))})
            return {"atlas":atlas["atlas"],"mesh":"fsaverage5","sha256":hashlib.sha256(raw).hexdigest(),"times":times,
                    "regions":regions,"interpretation":"Anatomical averages of model predictions; no cognitive function or emotion is inferred."}

    @app.get("/api/v2/publish/providers", dependencies=[Depends(human)])
    def publish_providers():
        return publishing.statuses()

    @app.post("/api/v2/publish/{provider}/connect", dependencies=[Depends(human)])
    def publish_connect(provider: str):
        return publishing.begin_oauth(provider)

    @app.get("/api/v2/publish/oauth/{provider}/callback")
    def publish_oauth_callback(provider: str, state: str = "", code: str = "", auth_code: str = "", error: str = ""):
        destination = settings.frontend_origin.rstrip("/") + "/publish/oauth-return"
        if provider not in PROVIDERS:
            return RedirectResponse(destination + "?status=error&code=UNKNOWN_PROVIDER", status_code=303)
        if error:
            return RedirectResponse(destination + "?status=error&code=AUTH_DENIED&provider=" + provider, status_code=303)
        authorization_code = code or auth_code
        if not state or not authorization_code:
            return RedirectResponse(destination + "?status=error&code=MISSING_CALLBACK_DATA&provider=" + provider, status_code=303)
        try:
            publishing.complete_oauth(provider, state, authorization_code)
            return RedirectResponse(destination + "?status=connected&provider=" + provider, status_code=303)
        except AdProviderFailure as exc:
            return RedirectResponse(destination + "?status=error&code=" + exc.code + "&provider=" + provider, status_code=303)
        except Exception:
            return RedirectResponse(destination + "?status=error&code=CONNECT_FAILED&provider=" + provider, status_code=303)

    @app.get("/api/v2/publish/{provider}/accounts", dependencies=[Depends(human)])
    def publish_accounts(provider: str):
        if provider not in PROVIDERS:
            raise DomainError("Unknown advertising provider", 404)
        return publishing.accounts(provider)

    @app.post("/api/v2/publish/{provider}/disconnect", dependencies=[Depends(human)])
    def publish_disconnect(provider: str):
        if provider not in PROVIDERS:
            raise DomainError("Unknown advertising provider", 404)
        return publishing.disconnect(provider)

    @app.get("/api/v2/publish/receipts", dependencies=[Depends(human)])
    def publish_receipts(campaign_id: str | None = None):
        return publishing.publications(campaign_id)

    @app.post("/api/v2/publish/sync", dependencies=[Depends(human)], status_code=201)
    def publish_sync(body: AdAssetSyncRequest):
        return publishing.sync_asset(body)

    @app.post("/api/v2/publish/receipts/{identity}/check", dependencies=[Depends(human)])
    def publish_check(identity: str):
        return publishing.check_meta_video(identity)

    @app.post("/api/v2/experiments", dependencies=[Depends(operator)], status_code=201)
    def experiment_create(body: DeploymentSpec):
        with store.transaction() as session:
            run = required(session, Run, body.run_id, lock=True)
            creative = required(session, Creative, body.creative_id)
            if creative.run_id != run.id or not creative.output_asset_id or run.state not in {"READY_FOR_REVIEW", "COMPLETE"}:
                raise DomainError("Only a completed, evaluated creative can enter human deployment review")
            evidence = engine._evidence(session, creative)
            if not evidence["eligible"]:
                raise DomainError("Creative does not pass required evidence and constraint gates")
            asset = required(session, Asset, creative.output_asset_id)
            review = {**body.model_dump(), "asset_sha256": asset.sha256, "asset_id": asset.id, "status": "PAUSED"}
            deployment = Deployment(id=uid(), run_id=run.id, spec=review, review_digest=digest(review), entities={}, metrics=[])
            session.add(deployment)
            session.flush()
            emit(session, run, "DEPLOYMENT_DRAFTED", experiment_id=deployment.id, review_digest=deployment.review_digest)
            return record(deployment)

    @app.get("/api/v2/experiments", dependencies=[Depends(operator)])
    def experiments():
        with store.read() as session:
            return [record(d) for d in session.scalars(select(Deployment).order_by(Deployment.created_at.desc()).limit(200))]

    @app.post("/api/v2/experiments/{identity}/approve", dependencies=[Depends(human)])
    def approve(identity: str, body: Approval):
        with store.transaction() as session:
            row = required(session, Deployment, identity, lock=True)
            if row.state != "DRAFT" or not hmac.compare_digest(row.review_digest, body.review_digest):
                raise DomainError("Approval digest does not match the current immutable review")
            if body.confirmation != "APPROVE PAUSED DEPLOYMENT":
                raise DomainError("Explicit paused-deployment confirmation is required", 422)
            if not row.spec["research_license_approved_for_commercial_use"]:
                raise DomainError("Commercial-use licensing must be reviewed before deployment", 422)
            row.state, row.approved_by, row.approved_at = "APPROVED", "human", now()
            emit(session, required(session, Run, row.run_id), "HUMAN_APPROVAL", experiment_id=row.id, review_digest=row.review_digest)
            return record(row)

    @app.post("/api/v2/experiments/{identity}/deploy", dependencies=[Depends(human)], status_code=202)
    def deploy(identity: str, body: Approval):
        if body.confirmation != "DEPLOY PAUSED":
            raise DomainError("Explicit DEPLOY PAUSED confirmation is required", 422)
        return meta.enqueue(identity, body.review_digest)

    @app.post("/api/v2/experiments/{identity}/insights", dependencies=[Depends(operator)])
    def insights(identity: str, since: str, until: str):
        try:
            return meta.insights(identity, since, until)
        except ValueError as exc:
            raise DomainError("Expected ISO dates and a valid reporting window", 422) from exc

    # No activate, increase-budget, billing, arbitrary-code, or policy-override route exists.
    return app
