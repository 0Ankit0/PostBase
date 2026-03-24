from __future__ import annotations

from collections.abc import Callable

from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.errors import ProviderResolutionError
from src.postbase.platform.contracts import CapabilityProfile, ProviderAdapter


ProviderFactory = Callable[[], ProviderAdapter]


class ProviderRegistry:
    def __init__(self) -> None:
        self._registry: dict[tuple[CapabilityKey, str], ProviderFactory] = {}

    def register(
        self,
        capability: CapabilityKey,
        provider_key: str,
        factory: ProviderFactory,
    ) -> None:
        self._registry[(capability, provider_key)] = factory

    def resolve(self, capability: CapabilityKey, provider_key: str) -> ProviderAdapter:
        factory = self._registry.get((capability, provider_key))
        if factory is None:
            raise ProviderResolutionError(
                f"No provider registered for capability={capability.value} provider={provider_key}"
            )
        return factory()

    def registered_profiles(self) -> list[tuple[CapabilityKey, str]]:
        return sorted(self._registry.keys(), key=lambda item: (item[0].value, item[1]))

    def profiles(self) -> list[CapabilityProfile]:
        profiles = [factory().profile() for factory in self._registry.values()]
        return sorted(profiles, key=lambda item: (item.capability.value, item.provider_key))


provider_registry = ProviderRegistry()
