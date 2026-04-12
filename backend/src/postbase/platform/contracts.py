from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.postbase.domain.enums import CapabilityKey


class ProviderHealth(BaseModel):
    ready: bool = True
    detail: str = "ok"


class CapabilityProfile(BaseModel):
    capability: CapabilityKey
    provider_key: str
    adapter_version: str = "1.0.0"
    conformance_version: str = "2026.03"
    supported_operations: list[str] = Field(default_factory=list)
    supported_regions: list[str] = Field(default_factory=lambda: ["global"])
    required_secret_kinds: list[str] = Field(default_factory=list)
    optional_features: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)


class ResolvedBinding(BaseModel):
    environment_id: int
    project_id: int
    capability: CapabilityKey
    provider_key: str
    adapter_version: str
    region: str | None = None
    resolved_secrets: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class ProviderAdapter(Protocol):
    def profile(self) -> CapabilityProfile:
        ...

    async def health(self) -> ProviderHealth:
        ...
