from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.domain.enums import ProviderCertificationState
from src.postbase.domain.models import CapabilityType, ProviderCatalogEntry
from src.postbase.platform.bootstrap import bootstrap_postbase_runtime
from src.postbase.platform.registry import provider_registry

CERTIFICATION_STATES: dict[tuple[str, str], ProviderCertificationState] = {
    ("auth", "local-postgres"): ProviderCertificationState.CERTIFIED,
    ("auth", "oidc-certified"): ProviderCertificationState.CERTIFIED,
    ("data", "postgres-native"): ProviderCertificationState.CERTIFIED,
    ("data", "postgres-compat"): ProviderCertificationState.CERTIFIED,
    ("storage", "s3-compatible"): ProviderCertificationState.CERTIFIED,
    ("storage", "local-disk"): ProviderCertificationState.EXPERIMENTAL,
    ("functions", "celery-runtime"): ProviderCertificationState.CERTIFIED,
    ("functions", "inline-runtime"): ProviderCertificationState.EXPERIMENTAL,
    ("events", "redis-pubsub"): ProviderCertificationState.CERTIFIED,
    ("events", "websocket-gateway"): ProviderCertificationState.EXPERIMENTAL,
}


async def seed_provider_catalog(db: AsyncSession) -> None:
    if not provider_registry.registered_profiles():
        bootstrap_postbase_runtime()

    capability_ids: dict[str, int] = {}
    for profile in provider_registry.profiles():
        capability_row = (
            await db.execute(select(CapabilityType).where(CapabilityType.key == profile.capability.value))
        ).scalars().first()
        if capability_row is None:
            capability_row = CapabilityType(
                key=profile.capability.value,
                facade_version="v1",
                description=f"{profile.capability.value} capability",
            )
            db.add(capability_row)
            await db.flush()
        capability_ids[profile.capability.value] = capability_row.id

    for profile in provider_registry.profiles():
        existing = (
            await db.execute(
                select(ProviderCatalogEntry).where(
                    ProviderCatalogEntry.capability_type_id == capability_ids[profile.capability.value],
                    ProviderCatalogEntry.provider_key == profile.provider_key,
                    ProviderCatalogEntry.adapter_version == profile.adapter_version,
                )
            )
        ).scalars().first()
        if existing is None:
            db.add(
                ProviderCatalogEntry(
                    capability_type_id=capability_ids[profile.capability.value],
                    provider_key=profile.provider_key,
                    adapter_version=profile.adapter_version,
                    certification_state=CERTIFICATION_STATES.get(
                        (profile.capability.value, profile.provider_key),
                        ProviderCertificationState.EXPERIMENTAL,
                    ),
                    metadata_json={
                        "seeded": True,
                        "conformance_version": profile.conformance_version,
                        "supported_regions": profile.supported_regions,
                        "required_secret_kinds": profile.required_secret_kinds,
                        "supported_operations": profile.supported_operations,
                        "optional_features": profile.optional_features,
                        "validation_checks": profile.validation_checks,
                        "limits": profile.limits,
                    },
                )
            )
    await db.commit()
