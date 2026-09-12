"""Explicit configuration; secrets never enter browser bundles or evidence records."""
import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

ROOT = Path(__file__).resolve().parents[2]
from dotenv import load_dotenv
load_dotenv(ROOT / '.env', override=False)


def _runtime_python(name: str) -> Path:
    executable = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    return ROOT / '.runtimes' / name / executable


def _default_model_python() -> Path:
    staged = _runtime_python('model')
    if staged.exists() or (ROOT / '.runtimes/active.json').is_file():
        return staged
    executable = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    return ROOT / 'tribev2-balanced-qv-local/.venv' / executable

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='NEUROLOOP_', env_file=ROOT / '.env', extra='ignore')
    root: Path = ROOT
    auth_token: str = Field(min_length=24)
    host: str = '127.0.0.1'
    port: int = 8010
    frontend_origin: str = 'http://localhost:3010'
    model_python: Path = _default_model_python()
    model_timeout_seconds: int = 900
    allow_model_downloads: bool = False
    tsam_enabled: bool = False
    tsam_research_license_accepted: bool = False
    database_url: str = ''
    max_upload_bytes: int = 200 * 1024 * 1024
    max_media_seconds: int = 60
    planner_url: str = 'https://api.inference.wandb.ai/v1'
    planner_model: str = 'openai/gpt-oss-20b'
    planner_enabled: bool = False
    research_url: str = 'http://localhost:2718'
    research_enabled: bool = False
    weave_enabled: bool = False
    mcp_allowed_hosts: list[str] = ['localhost:*', '127.0.0.1:*', 'testserver']
    mcp_allowed_origins: list[str] = ['http://localhost:*', 'http://127.0.0.1:*']

    @property
    def data(self) -> Path:
        return self.root / 'data'

    @property
    def db_url(self) -> str:
        return self.database_url or f'sqlite:///{(self.data / "neuroloop.db").as_posix()}'

    def prepare(self) -> None:
        for name in ['assets', 'results', 'renders', 'logs', 'geometry', 'tmp', 'exports']:
            (self.data / name).mkdir(parents=True, exist_ok=True)

@lru_cache
def settings() -> Settings:
    s = Settings()
    s.prepare()
    return s
