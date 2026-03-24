from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.domain.enums import BindingStatus, CapabilityKey
from src.postbase.domain.models import CapabilityBinding, CapabilityType, ProviderCatalogEntry
from src.postbase.platform.contracts import ResolvedBinding


async def resolve_active_binding(
    db: AsyncSession,
    *,
    environment_id: int,
    project_id: int,
    capability: CapabilityKey,
) -> ResolvedBinding:
    row = (
        await db.execute(
            select(CapabilityBinding, ProviderCatalogEntry)
            .join(CapabilityType, CapabilityBinding.capability_type_id == CapabilityType.id)
            .join(
                ProviderCatalogEntry,
                CapabilityBinding.provider_catalog_entry_id == ProviderCatalogEntry.id,
            )
            .where(
                CapabilityBinding.environment_id == environment_id,
                CapabilityType.key == capability.value,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active binding for capability '{capability.value}'",
        )
    binding, provider = row
    if binding.status != BindingStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Capability '{capability.value}' is not currently active for this environment",
        )
    return ResolvedBinding(
        environment_id=environment_id,
        project_id=project_id,
        capability=capability,
        provider_key=provider.provider_key,
        adapter_version=provider.adapter_version,
        config=binding.config_json,
    )
