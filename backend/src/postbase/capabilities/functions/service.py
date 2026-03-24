from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.errors import ProviderResolutionError
from src.postbase.platform.registry import provider_registry
from src.postbase.platform.resolver import resolve_active_binding


class FunctionsFacade:
    async def resolve_provider(self, context):
        if not provider_registry.registered_profiles():
            from src.postbase.platform.bootstrap import bootstrap_postbase_runtime
            bootstrap_postbase_runtime()
        binding = await resolve_active_binding(
            context.db,  # type: ignore[attr-defined]
            environment_id=context.environment_id,
            project_id=context.project_id,
            capability=CapabilityKey.FUNCTIONS,
        )
        try:
            return provider_registry.resolve(CapabilityKey.FUNCTIONS, binding.provider_key)
        except ProviderResolutionError as exc:
            raise RuntimeError(str(exc)) from exc
