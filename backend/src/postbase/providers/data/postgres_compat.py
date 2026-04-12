from __future__ import annotations

from src.postbase.domain.enums import CapabilityKey
from src.postbase.platform.contracts import CapabilityProfile
from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider


class PostgresCompatDataProvider(PostgresNativeDataProvider):
    def profile(self) -> CapabilityProfile:
        profile = super().profile()
        return CapabilityProfile(
            capability=CapabilityKey.DATA,
            provider_key="postgres-compat",
            supported_operations=profile.supported_operations,
            optional_features=profile.optional_features,
            adapter_version=profile.adapter_version,
            conformance_version=profile.conformance_version,
            supported_regions=profile.supported_regions,
            required_secret_kinds=profile.required_secret_kinds,
            limits=profile.limits,
        )
