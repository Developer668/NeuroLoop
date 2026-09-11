"""Generation-provider contracts. Sponsor-gated providers fail closed until configured."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    status: str
    detail: str
    capabilities: tuple[str, ...] = ()


class GenerationProvider(Protocol):
    def status(self) -> ProviderStatus: ...
    def generate(self, request: dict) -> dict: ...


class DeferredProvider:
    def __init__(self, name: str, detail: str, capabilities: tuple[str, ...]):
        self._status = ProviderStatus(name, "awaiting_sponsor_access", detail, capabilities)

    def status(self) -> ProviderStatus:
        return self._status

    def generate(self, request: dict) -> dict:
        raise RuntimeError(f"{self._status.name} is not configured. {self._status.detail}")


def statuses() -> list[dict]:
    providers = [
        DeferredProvider("Ideogram 4", "Image generation is intentionally deferred until sponsor credits/API access are available.", ("image_generate", "image_edit", "variations")),
        DeferredProvider("MiniMax H3", "Video generation is intentionally deferred until sponsor credits/model access are available.", ("video_generate", "video_edit", "audio_video")),
    ]
    return [p.status().__dict__ for p in providers]
