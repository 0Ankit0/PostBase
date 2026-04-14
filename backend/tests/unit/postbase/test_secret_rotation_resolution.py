from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.apps.core.config import settings
from src.apps.iam.models.user import User
from src.postbase.control_plane.service import set_binding_status
from src.postbase.domain.enums import BindingStatus, CapabilityKey, SecretStatus
from src.postbase.domain.models import (
    BindingSecretRef,
    CapabilityBinding,
    CapabilityType,
    Environment,
    Project,
    ProviderCatalogEntry,
    SecretRef,
)
from src.postbase.platform.resolver import resolve_active_binding
from src.postbase.platform.secret_store import DbEncryptedSecretStore


@pytest.mark.asyncio
async def test_resolver_uses_latest_valid_secret_version_with_fallback(db_session) -> None:
    store = DbEncryptedSecretStore(settings.POSTBASE_SECRET_ENCRYPTION_KEY)
    project = Project(tenant_id=1, name="proj", slug="proj")
    db_session.add(project)
    await db_session.flush()
    environment = Environment(project_id=project.id, name="env", slug="env")
    db_session.add(environment)
    capability = CapabilityType(key=CapabilityKey.STORAGE.value)
    db_session.add(capability)
    await db_session.flush()
    provider = ProviderCatalogEntry(
        capability_type_id=capability.id,
        provider_key="s3-compatible",
        metadata_json={"required_secret_kinds": ["access_key"]},
    )
    db_session.add(provider)
    await db_session.flush()
    binding = CapabilityBinding(
        environment_id=environment.id,
        capability_type_id=capability.id,
        provider_catalog_entry_id=provider.id,
        status=BindingStatus.ACTIVE,
    )
    db_session.add(binding)
    await db_session.flush()

    v1 = SecretRef(
        environment_id=environment.id,
        name="s3-key",
        provider_key="s3-compatible",
        secret_kind="access_key",
        version=1,
        is_active_version=False,
        status=SecretStatus.ACTIVE,
        encrypted_value=store.encrypt("v1-secret"),
        value_hash="h1",
        last_four="cret",
        rotated_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    v2 = SecretRef(
        environment_id=environment.id,
        name="s3-key",
        provider_key="s3-compatible",
        secret_kind="access_key",
        version=2,
        is_active_version=True,
        status=SecretStatus.ACTIVE,
        encrypted_value=store.encrypt("v2-secret"),
        value_hash="h2",
        last_four="cret",
        rotated_at=datetime.now(timezone.utc) - timedelta(days=1),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(v1)
    db_session.add(v2)
    await db_session.flush()
    db_session.add(BindingSecretRef(binding_id=binding.id, secret_ref_id=v1.id))
    await db_session.commit()

    resolved = await resolve_active_binding(
        db_session,
        environment_id=environment.id,
        project_id=project.id,
        capability=CapabilityKey.STORAGE,
    )
    assert resolved.resolved_secrets["access_key"] == "v2-secret"

    v2.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    resolved_after_expiry = await resolve_active_binding(
        db_session,
        environment_id=environment.id,
        project_id=project.id,
        capability=CapabilityKey.STORAGE,
    )
    assert resolved_after_expiry.resolved_secrets["access_key"] == "v1-secret"


@pytest.mark.asyncio
async def test_activation_blocked_when_required_secret_is_expired(db_session) -> None:
    actor = User(username="admin", email="admin@example.com", hashed_password="hash")
    db_session.add(actor)
    await db_session.flush()

    project = Project(tenant_id=1, name="proj2", slug="proj2")
    db_session.add(project)
    await db_session.flush()
    environment = Environment(project_id=project.id, name="env2", slug="env2")
    db_session.add(environment)
    capability = CapabilityType(key=CapabilityKey.STORAGE.value)
    db_session.add(capability)
    await db_session.flush()
    provider = ProviderCatalogEntry(
        capability_type_id=capability.id,
        provider_key="s3-compatible",
        metadata_json={"required_secret_kinds": ["access_key"]},
    )
    db_session.add(provider)
    await db_session.flush()

    binding = CapabilityBinding(
        environment_id=environment.id,
        capability_type_id=capability.id,
        provider_catalog_entry_id=provider.id,
        status=BindingStatus.PENDING_VALIDATION,
    )
    db_session.add(binding)
    await db_session.flush()

    expired_secret = SecretRef(
        environment_id=environment.id,
        name="s3-key",
        provider_key="s3-compatible",
        secret_kind="access_key",
        version=1,
        is_active_version=True,
        status=SecretStatus.ACTIVE,
        encrypted_value="enc",
        value_hash="hash",
        last_four="0000",
        rotated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(expired_secret)
    await db_session.flush()
    db_session.add(BindingSecretRef(binding_id=binding.id, secret_ref_id=expired_secret.id))
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await set_binding_status(
            db_session,
            binding=binding,
            status_value=BindingStatus.ACTIVE,
            reason="activate",
            actor=actor,
            project=project,
            environment=environment,
        )

    assert exc.value.status_code == 409
    assert "missing or expired secrets" in str(exc.value.detail)
