"""Durable SQL state. SQLite is the single-machine deployment; PostgreSQL is supported."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import create_engine, event, String, Text, Float, Integer, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings

def uid() -> str:
    return str(uuid.uuid4())

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

class Base(DeclarativeBase):
    pass

class Asset(Base):
    __tablename__ = 'assets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(20))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    brief: Mapped[str] = mapped_column(Text, default='')
    asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reference_ids: Mapped[list] = mapped_column(JSON, default=list)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Run(Base):
    __tablename__ = 'runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    mode: Mapped[str] = mapped_column(String(20), default='analyze')
    status: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(80), default='Waiting for worker')
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluations_used: Mapped[int] = mapped_column(Integer, default=0)
    max_evaluations: Mapped[int] = mapped_column(Integer, default=4)
    compute_seconds: Mapped[float] = mapped_column(Float, default=0)
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)
    owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    heartbeat: Mapped[str | None] = mapped_column(String(40), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, default=uid)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class Evaluation(Base):
    __tablename__ = 'evaluations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    evaluator: Mapped[str] = mapped_column(String(80))
    profile: Mapped[str] = mapped_column(String(160))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    prediction_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Experiment(Base):
    __tablename__ = 'experiments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    operator: Mapped[str] = mapped_column(String(80))
    hypothesis: Mapped[str] = mapped_column(Text)
    specification: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    baseline_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String(24), default='proposed')
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class PolicyStat(Base):
    __tablename__ = 'policy_stats'
    key: Mapped[str] = mapped_column(String(240), primary_key=True)
    context: Mapped[str] = mapped_column(String(160))
    operator: Mapped[str] = mapped_column(String(80))
    successes: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    total_gain: Mapped[float] = mapped_column(Float, default=0)
    total_seconds: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)

class RunEvent(Base):
    __tablename__ = 'run_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class SchemaVersion(Base):
    __tablename__ = 'schema_version'
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    installed_at: Mapped[str] = mapped_column(String(40), default=now)

class ArchivedRecord(Base):
    """Retire workspace entries while preserving their research evidence."""
    __tablename__ = 'archived_records'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    record_id: Mapped[str] = mapped_column(String(36), index=True)
    archived_at: Mapped[str] = mapped_column(String(40), default=now)

s = settings()
engine = create_engine(s.db_url, connect_args={'check_same_thread': False, 'timeout': 30} if s.db_url.startswith('sqlite') else {}, pool_pre_ping=True)
if s.db_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_pragmas(connection, _):
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.close()
Session = sessionmaker(engine, expire_on_commit=False)

def initialize() -> None:
    from sqlalchemy import inspect, text
    from .migrations import MIGRATIONS
    if inspect(engine).has_table('schema_version'):
        with engine.connect() as connection:
            if connection.execute(text('SELECT COALESCE(MAX(version),0) FROM schema_version')).scalar_one() > max(MIGRATIONS):
                raise RuntimeError('Database belongs to a newer NeuroLoop release; upgrade the application.')
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        if db.get(SchemaVersion, 1) is None:
            db.add(SchemaVersion(version=1))
    from .migrations import upgrade
    upgrade(engine)

def as_dict(record: Base, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    return {c.name: getattr(record, c.name) for c in record.__table__.columns if c.name not in exclude}

def emit(run_id: str, kind: str, message: str, **details: Any) -> None:
    with Session.begin() as db:
        db.add(RunEvent(run_id=run_id, kind=kind, message=message, details=details))
