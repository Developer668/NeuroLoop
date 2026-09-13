"""Transactional state. SQLite is explicitly development-only; PostgreSQL is production.

SQLite writers use BEGIN IMMEDIATE; PostgreSQL locks the run before transitions.
External/model calls never occur inside database transactions.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from .config import Settings
from .domain import now, uid


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    spec: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Run(Base):
    __tablename__ = "campaign_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(250), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(40), default="CREATED")
    round: Mapped[int] = mapped_column(Integer, default=0)
    selected_ids: Mapped[list] = mapped_column(JSON, default=list)
    champion_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now)


class Asset(Base):
    __tablename__ = "creative_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    upload_key: Mapped[str | None] = mapped_column(String(250), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(30))
    mime: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Creative(Base):
    __tablename__ = "creatives"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    round: Mapped[int] = mapped_column(Integer)
    branch: Mapped[int] = mapped_column(Integer)
    creation_type: Mapped[str] = mapped_column(String(30))
    plan: Mapped[dict] = mapped_column(JSON)
    input_asset_ids: Mapped[list] = mapped_column(JSON)
    output_asset_id: Mapped[str | None] = mapped_column(ForeignKey("creative_assets.id"), nullable=True)
    generation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="QUEUED")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribution_quality: Mapped[str] = mapped_column(String(30), default="variant_level")
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Job(Base):
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    capability: Mapped[str] = mapped_column(String(40), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(250), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[float] = mapped_column(Float, default=now)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id"), unique=True)
    evaluator: Mapped[str] = mapped_column(String(40))
    comparison_key: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class ArtifactBackup(Base):
    __tablename__ = "artifact_backups"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_attempt: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[float] = mapped_column(Float, default=now)


class NotebookEvidence(Base):
    """Imported, immutable notebook evidence; never grants campaign eligibility."""
    __tablename__ = "notebook_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    input_asset_id: Mapped[str] = mapped_column(ForeignKey("creative_assets.id"), index=True)
    source_receipt: Mapped[str] = mapped_column(String(300), unique=True)
    source_kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(250))
    evaluator: Mapped[str] = mapped_column(String(40))
    comparison_key: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id"), unique=True)
    evidence: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    applied_action: Mapped[str] = mapped_column(String(40))
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Feedback(Base):
    __tablename__ = "human_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"))
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Event(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Worker(Base):
    __tablename__ = "notebook_workers"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    capabilities: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(100))
    workload_approved: Mapped[bool] = mapped_column(Boolean)
    heartbeat_at: Mapped[float] = mapped_column(Float, default=now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Trace(Base):
    __tablename__ = "weave_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    exception: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[float] = mapped_column(Float, default=now)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    delivered_revision: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="PENDING")
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class Intervention(Base):
    __tablename__ = "intervention_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"), unique=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    context_key: Mapped[str] = mapped_column(String(64), index=True)
    strategy: Mapped[str] = mapped_column(String(160))
    observation: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class PolicyProposal(Base):
    __tablename__ = "strategy_policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="PROPOSED")
    validation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Deployment(Base):
    __tablename__ = "meta_experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("campaign_runs.id"), index=True)
    spec: Mapped[dict] = mapped_column(JSON)
    review_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(40), default="DRAFT")
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    entities: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)


Index("ix_jobs_claim", Job.status, Job.available_at, Job.capability)


def record(row: Any) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        sqlite = settings.db_url.startswith("sqlite")
        self.engine = create_engine(settings.db_url, connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {}, pool_pre_ping=True)
        if sqlite:
            @event.listens_for(self.engine, "connect")
            def configure(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=30000")
        self.sqlite = sqlite

    def initialize(self):
        if self.settings.auto_migrate:
            Base.metadata.create_all(self.engine)
        else:
            from sqlalchemy import inspect
            if "campaign_runs" not in inspect(self.engine).get_table_names():
                raise RuntimeError("Database not migrated. Run: alembic upgrade head")

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                if self.sqlite:
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    @contextmanager
    def read(self):
        with Session(self.engine, expire_on_commit=False) as session:
            yield session
