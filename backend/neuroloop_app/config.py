"""Explicit app/worker configuration. This package never loads neural weights."""
from pathlib import Path
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEUROLOOP_", env_file=ROOT / ".env", extra="ignore")
    data_dir: Path = ROOT / "data" / "v2"
    database_url: str = ""
    environment: str = "development"
    operator_token: SecretStr = SecretStr("")
    agent_token: SecretStr = SecretStr("")
    worker_token: SecretStr = SecretStr("")
    local_bootstrap_token: SecretStr = SecretStr("")
    signing_key: SecretStr = SecretStr("")
    frontend_origin: str = "http://localhost:3010"
    public_api_url: str = "http://127.0.0.1:8010"
    session_seconds: int = 28800
    auto_migrate: bool = True
    max_upload_bytes: int = 200 * 1024 * 1024
    max_request_bytes: int = 2 * 1024 * 1024
    max_media_seconds: int = 60
    max_pixels: int = 33_177_600
    lease_seconds: int = Field(default=120, ge=10, le=3600)
    worker_stale_seconds: int = 150
    max_job_attempts: int = 3
    rate_limit_per_minute: int = 240
    storage: str = "local"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    ffprobe: str = "ffprobe"
    ffmpeg: str = "ffmpeg"
    weave_enabled: bool = False
    wandb_artifacts_enabled: bool = False
    wandb_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="WANDB_API_KEY")
    wandb_project: str = Field(default="", validation_alias="WANDB_PROJECT")
    inference_model: str = ""
    inference_max_tokens: int = Field(default=32768, ge=1024, le=32768)
    inference_timeout_seconds: float = Field(default=600, ge=30, le=900)
    reasoner_cost_ceiling_usd: float | None = Field(default=None, ge=0)
    typesafe_cost_ceiling_usd: float | None = Field(default=None, ge=0)
    typesafe_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="TYPESAFE_API_KEY")
    typesafe_model: str = "jev-latest"
    provider: str = "local"
    provider_workload_approved: bool = False
    model_long_edge: int = Field(default=1024, ge=512, le=2048)
    model_steps: int = Field(default=4, ge=4, le=30)
    worker_idle_seconds: int = Field(default=300, ge=30, le=3600)
    vision_model: str = ""
    vision_revision: str = "operator-configured-v1"
    vision_max_tokens: int = Field(default=32768, ge=1024, le=32768)
    enable_h3: bool = False
    enable_ideogram: bool = False
    enable_legacy_evaluators: bool = False
    research_root: Path = ROOT
    research_bundle_path: Path | None = None
    tsam_research_license_accepted: bool = False
    meta_access_token: SecretStr = Field(default=SecretStr(""), validation_alias="META_ACCESS_TOKEN")
    meta_graph_version: str = ""

    @model_validator(mode="after")
    def validate_deployment(self):
        if self.storage not in {"local", "s3"}:
            raise ValueError("storage must be local or s3")
        if self.environment == "production":
            if not all(getattr(self, field).get_secret_value() for field in ("operator_token", "worker_token", "signing_key")):
                raise ValueError("Production requires operator, worker and signing credentials")
            if not self.public_api_url.startswith("https://"):
                raise ValueError("Production requires an HTTPS public API URL")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if self.auto_migrate:
                raise ValueError("Production requires explicit Alembic migrations")
            if self.storage != "s3":
                raise ValueError("Production requires S3-compatible storage")
            if not self.frontend_origin.startswith("https://"):
                raise ValueError("Production requires HTTPS")
        for name in ("operator_token", "agent_token", "worker_token", "local_bootstrap_token", "signing_key"):
            value = getattr(self, name).get_secret_value()
            if value and len(value) < 32:
                raise ValueError(f"{name} must have at least 32 characters")
        configured = [getattr(self, name).get_secret_value() for name in ("operator_token", "agent_token", "worker_token")]
        configured = [value for value in configured if value]
        if len(configured) != len(set(configured)):
            raise ValueError("Human, agent and worker credentials must be different")
        return self

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'neuroloop.sqlite3').as_posix()}"
