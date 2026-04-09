from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.domain.enums import BindingStatus, CapabilityKey, SecretStatus
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
    anchor_secret_rows = (
        await db.execute(
            select(SecretRef)
            .join(BindingSecretRef, BindingSecretRef.secret_ref_id == SecretRef.id)
            .where(BindingSecretRef.binding_id == binding.id)
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    resolved_secrets: dict[str, str] = {}
    for anchor in anchor_secret_rows:
        latest_valid = (
            await db.execute(
                select(SecretRef)
                .where(
                    SecretRef.environment_id == anchor.environment_id,
                    SecretRef.name == anchor.name,
                    SecretRef.provider_key == anchor.provider_key,
                    SecretRef.secret_kind == anchor.secret_kind,
                    SecretRef.status == SecretStatus.ACTIVE,
                    (SecretRef.expires_at.is_(None) | (SecretRef.expires_at > now)),
                )
                .order_by(
                    SecretRef.is_active_version.desc(),
                    SecretRef.version.desc(),
                    SecretRef.updated_at.desc(),
                )
            )
        ).scalars().first()
        if latest_valid is not None:
            resolved_secrets[latest_valid.secret_kind] = secret_store.decrypt(latest_valid.encrypted_value)
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
