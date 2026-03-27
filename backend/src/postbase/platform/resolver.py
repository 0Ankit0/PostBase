from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.domain.enums import BindingStatus, CapabilityKey
from src.apps.core.config import settings
from src.postbase.domain.models import (
    BindingSecretRef,
    CapabilityBinding,
    CapabilityType,
    ProviderCatalogEntry,
    SecretRef,
)
from src.postbase.platform.contracts import ResolvedBinding
from src.postbase.platform.secret_store import DbEncryptedSecretStore


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
                CapabilityBinding.status == BindingStatus.ACTIVE,
            )
            .order_by(CapabilityBinding.updated_at.desc())
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active binding for capability '{capability.value}'",
        )
    binding, provider = row
    secret_store = DbEncryptedSecretStore(settings.POSTBASE_SECRET_ENCRYPTION_KEY)
    secret_rows = (
        await db.execute(
            select(SecretRef)
            .join(BindingSecretRef, BindingSecretRef.secret_ref_id == SecretRef.id)
            .where(BindingSecretRef.binding_id == binding.id)
        )
    ).scalars().all()
    resolved_secrets = {item.secret_kind: secret_store.decrypt(item.encrypted_value) for item in secret_rows}
    return ResolvedBinding(
        environment_id=environment_id,
        project_id=project_id,
        capability=capability,
        provider_key=provider.provider_key,
        adapter_version=provider.adapter_version,
        region=binding.region,
        resolved_secrets=resolved_secrets,
        config=binding.config_json,
    )
