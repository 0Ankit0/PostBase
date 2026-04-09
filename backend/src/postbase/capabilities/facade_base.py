from __future__ import annotations

from src.postbase.capabilities.contracts import FacadeStatusResponse
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.errors import ProviderResolutionError
from src.postbase.platform.registry import provider_registry
from src.postbase.platform.resolver import resolve_active_binding


class CapabilityFacadeBase:
    capability: CapabilityKey

    async def resolve_provider(self, context):
        if not provider_registry.registered_profiles():
            from src.postbase.platform.bootstrap import bootstrap_postbase_runtime

            bootstrap_postbase_runtime()
        binding = await resolve_active_binding(
            context.db,  # type: ignore[attr-defined]
            environment_id=context.environment_id,
            project_id=context.project_id,
            capability=self.capability,
        )
        try:
            return provider_registry.resolve(self.capability, binding.provider_key)
        except ProviderResolutionError as exc:
            raise RuntimeError(str(exc)) from exc

    async def status(self, context) -> FacadeStatusResponse:
        try:
            provider = await self.resolve_provider(context)
        except Exception as exc:
            return FacadeStatusResponse(status="error", reason=str(exc))
        try:
            health = await provider.health()
        except Exception as exc:
            return FacadeStatusResponse(
                status="error",
                reason=f"health check failed: {exc}",
                provider_key=provider.profile().provider_key,
            )
        return FacadeStatusResponse(
            status="ready" if health.ready else "degraded",
            reason=health.detail,
            provider_key=provider.profile().provider_key,
        )
