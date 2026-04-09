from __future__ import annotations

from datetime import timezone, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import decode_id_or_404, encode_id
from src.apps.multitenancy.models.tenant import TenantMember, TenantRole
from src.postbase.domain.enums import (
    ApiKeyRole,
    BindingStatus,
    CapabilityKey,
    EnvironmentStage,
    EnvironmentStatus,
    MigrationStatus,
    PolicyMode,
    ReadinessState,
    SecretStatus,
    SwitchoverStatus,
)
from src.postbase.domain.models import (
    AuditLog,
    BindingSecretRef,
    CapabilityBinding,
    CapabilityType,
    DataNamespace,
    Environment,
    EnvironmentApiKey,
    Project,
    ProviderCatalogEntry,
    SchemaMigration,
    SecretRef,
    SwitchoverPlan,
    TableDefinition,
    UsageMeter,
)
from src.postbase.platform.access import (
    build_physical_schema,
    issue_environment_api_key,
    validate_identifier,
)
from src.postbase.platform.audit import record_audit_event
from src.postbase.platform.contracts import CapabilityProfile
from src.postbase.platform.registry import provider_registry
from src.postbase.platform.resolver import resolve_active_binding
from src.postbase.platform.seeding import seed_provider_catalog
from src.postbase.platform.security import hash_secret
from src.postbase.platform.secret_store import DbEncryptedSecretStore
from src.apps.core.config import settings


ROLE_ORDER = {TenantRole.MEMBER: 0, TenantRole.ADMIN: 1, TenantRole.OWNER: 2}
REQUIRED_OPERATIONS: dict[CapabilityKey, set[str]] = {
    CapabilityKey.AUTH: {"signup", "login", "refresh", "me", "logout"},
    CapabilityKey.DATA: {"namespaces", "tables", "crud"},
    CapabilityKey.STORAGE: {"upload", "list", "signed_url", "delete"},
    CapabilityKey.FUNCTIONS: {"create", "list", "invoke", "executions"},
    CapabilityKey.EVENTS: {"channels", "subscriptions", "publish"},
}
LEGAL_BINDING_STATUS_TRANSITIONS: dict[BindingStatus, set[BindingStatus]] = {
    BindingStatus.PENDING_VALIDATION: {
        BindingStatus.ACTIVE,
        BindingStatus.FAILED,
        BindingStatus.DISABLED,
    },
    BindingStatus.ACTIVE: {
        BindingStatus.DEPRECATED,
        BindingStatus.FAILED,
        BindingStatus.DISABLED,
        BindingStatus.RETIRED,
    },
    BindingStatus.DEPRECATED: {
        BindingStatus.ACTIVE,
        BindingStatus.DISABLED,
        BindingStatus.RETIRED,
    },
    BindingStatus.FAILED: {
        BindingStatus.PENDING_VALIDATION,
        BindingStatus.ACTIVE,
        BindingStatus.DISABLED,
        BindingStatus.RETIRED,
    },
    BindingStatus.DISABLED: {
        BindingStatus.PENDING_VALIDATION,
        BindingStatus.ACTIVE,
        BindingStatus.RETIRED,
    },
    BindingStatus.RETIRED: set(),
    BindingStatus.PENDING: {
        BindingStatus.PENDING_VALIDATION,
        BindingStatus.ACTIVE,
        BindingStatus.FAILED,
        BindingStatus.DISABLED,
    },
}


def _forbidden_role_payload(*, required_role: TenantRole) -> dict[str, str]:
    return {
        "code": "control_plane_forbidden",
        "message": "insufficient_role",
        "required_role": required_role.value,
    }


def _invalid_binding_transition_payload(
    *,
    binding_id: int,
    current_status: BindingStatus,
    target_status: BindingStatus,
) -> dict[str, object]:
    return {
        "code": "binding_invalid_status_transition",
        "message": "invalid_status_transition",
        "binding_id": encode_id(binding_id),
        "from_status": current_status.value,
        "to_status": target_status.value,
    }


def _active_binding_conflict_payload(
    *,
    binding_id: int,
    conflicting_binding_id: int,
) -> dict[str, object]:
    return {
        "code": "binding_active_uniqueness_conflict",
        "message": "active_binding_conflict",
        "binding_id": encode_id(binding_id),
        "conflicting_binding_id": encode_id(conflicting_binding_id),
    }


def _assert_binding_transition_is_legal(
    *,
    binding_id: int,
    current_status: BindingStatus,
    target_status: BindingStatus,
) -> None:
    if current_status == target_status:
        return
    allowed_targets = LEGAL_BINDING_STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed_targets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_invalid_binding_transition_payload(
                binding_id=binding_id,
                current_status=current_status,
                target_status=target_status,
            ),
        )


def _is_active_binding_uniqueness_error(exc: IntegrityError) -> bool:
    message = str(exc.orig).lower()
    return (
        "uq_postbase_capability_binding_active_per_capability_env" in message
        or "postbase_capability_binding.environment_id, postbase_capability_binding.capability_type_id" in message
    )


async def require_tenant_role(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    min_role: TenantRole = TenantRole.MEMBER,
) -> TenantMember:
    membership = (
        await db.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == user_id,
                TenantMember.is_active == True,
            )
        )
    ).scalars().first()
    if membership is None or ROLE_ORDER[membership.role] < ROLE_ORDER[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_forbidden_role_payload(required_role=min_role),
        )
    return membership


async def require_project_access(
    db: AsyncSession,
    *,
    project: Project,
    user_id: int,
    min_role: TenantRole = TenantRole.MEMBER,
) -> None:
    await require_tenant_role(db, tenant_id=project.tenant_id, user_id=user_id, min_role=min_role)


async def ensure_environment_access(
    db: AsyncSession,
    *,
    environment: Environment,
    user_id: int,
    min_role: TenantRole = TenantRole.MEMBER,
) -> Project:
    project = await db.get(Project, environment.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=user_id, min_role=min_role)
    return project


async def create_project_for_tenant(
    db: AsyncSession,
    *,
    tenant_id_hash: str,
    name: str,
    slug: str,
    description: str,
    actor: User,
) -> Project:
    tenant_id = decode_id_or_404(tenant_id_hash)
    await require_tenant_role(db, tenant_id=tenant_id, user_id=actor.id, min_role=TenantRole.ADMIN)
    slug = validate_identifier(slug, "Project slug")

    existing = (
        await db.execute(
            select(Project).where(Project.tenant_id == tenant_id, Project.slug == slug)
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project slug already exists")

    project = Project(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        description=description,
    )
    db.add(project)
    await db.flush()
    await record_audit_event(
        db,
        action="project.created",
        entity_type="project",
        entity_id=str(project.id),
        actor_user_id=actor.id,
        tenant_id=tenant_id,
        project_id=project.id,
        payload={"name": name, "slug": slug},
    )
    await db.commit()
    await db.refresh(project)
    return project


async def create_environment_for_project(
    db: AsyncSession,
    *,
    project_id_hash: str,
    name: str,
    slug: str,
    stage: str,
    region_preference: str | None,
    actor: User,
) -> Environment:
    await seed_provider_catalog(db)
    project_id = decode_id_or_404(project_id_hash)
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=actor.id, min_role=TenantRole.ADMIN)

    slug = validate_identifier(slug, "Environment slug")
    existing = (
        await db.execute(
            select(Environment).where(Environment.project_id == project_id, Environment.slug == slug)
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Environment slug already exists")

    environment = Environment(
        project_id=project_id,
        name=name,
        slug=slug,
        stage=stage,
        region_preference=region_preference,
        status=EnvironmentStatus.ACTIVE,
        readiness_state=ReadinessState.READY,
        readiness_detail="seeded with default active bindings",
        last_validated_at=datetime.now(timezone.utc),
    )
    db.add(environment)
    await db.flush()
    await _seed_environment_bindings(db, environment.id)
    for role_name in (ApiKeyRole.ANON, ApiKeyRole.SERVICE_ROLE):
        await issue_environment_api_key(
            db,
            environment_id=environment.id,
            name=role_name.value,
            role=role_name,
        )
    await record_audit_event(
        db,
        action="environment.created",
        entity_type="environment",
        entity_id=str(environment.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"name": name, "slug": slug, "stage": stage},
    )
    await db.commit()
    await db.refresh(environment)
    return environment


async def _seed_environment_bindings(db: AsyncSession, environment_id: int) -> None:
    capability_types = (await db.execute(select(CapabilityType))).scalars().all()
    for capability_type in capability_types:
        existing_binding = (
            await db.execute(
                select(CapabilityBinding).where(
                    CapabilityBinding.environment_id == environment_id,
                    CapabilityBinding.capability_type_id == capability_type.id,
                )
            )
        ).scalars().first()
        if existing_binding is not None:
            continue
        provider_entry = (
            await db.execute(
                select(ProviderCatalogEntry)
                .where(ProviderCatalogEntry.capability_type_id == capability_type.id)
                .order_by(ProviderCatalogEntry.id.asc())
            )
        ).scalars().first()
        if provider_entry is None:
            continue
        db.add(
            CapabilityBinding(
                environment_id=environment_id,
                capability_type_id=capability_type.id,
                provider_catalog_entry_id=provider_entry.id,
                status=BindingStatus.ACTIVE,
                readiness_detail="seed default binding",
            )
        )
    await db.flush()


async def create_secret_ref(
    db: AsyncSession,
    *,
    environment: Environment,
    project: Project,
    actor: User,
    name: str,
    provider_key: str,
    secret_kind: str,
    secret_value: str,
) -> SecretRef:
    secret_store = DbEncryptedSecretStore(settings.POSTBASE_SECRET_ENCRYPTION_KEY)
    validate_identifier(name, "Secret name")
    existing = (
        await db.execute(
            select(SecretRef).where(
                SecretRef.environment_id == environment.id,
                SecretRef.name == name,
            )
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Secret already exists")

    secret_ref = SecretRef(
        environment_id=environment.id,
        name=name,
        provider_key=provider_key,
        secret_kind=secret_kind,
        encrypted_value=secret_store.encrypt(secret_value),
        value_hash=hash_secret(secret_value),
        last_four=secret_value[-4:] if secret_value else "",
    )
    db.add(secret_ref)
    await db.flush()
    await record_audit_event(
        db,
        action="secret.created",
        entity_type="secret_ref",
        entity_id=str(secret_ref.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"name": name, "provider_key": provider_key},
    )
    await db.commit()
    await db.refresh(secret_ref)
    return secret_ref


async def rotate_secret_ref(
    db: AsyncSession,
    *,
    secret_ref: SecretRef,
    project: Project,
    environment: Environment,
    actor: User,
    secret_value: str,
) -> SecretRef:
    impacted_bindings = await _list_bindings_using_secret(db, secret_ref_id=secret_ref.id)
    if not impacted_bindings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret is not linked to any binding; link before rotation to avoid blind rotation",
        )

    secret_store = DbEncryptedSecretStore(settings.POSTBASE_SECRET_ENCRYPTION_KEY)
    previous_encrypted_value = secret_ref.encrypted_value
    previous_hash = secret_ref.value_hash
    previous_last_four = secret_ref.last_four
    secret_ref.encrypted_value = secret_store.encrypt(secret_value)
    secret_ref.value_hash = hash_secret(secret_value)
    secret_ref.last_four = secret_value[-4:] if secret_value else ""
    secret_ref.status = SecretStatus.ACTIVE
    touch_updated_at(secret_ref)
    try:
        await db.flush()
    except Exception as exc:
        secret_ref.encrypted_value = previous_encrypted_value
        secret_ref.value_hash = previous_hash
        secret_ref.last_four = previous_last_four
        touch_updated_at(secret_ref)
        await record_audit_event(
            db,
            action="secret.rotation_failed",
            entity_type="secret_ref",
            entity_id=str(secret_ref.id),
            actor_user_id=actor.id,
            tenant_id=project.tenant_id,
            project_id=project.id,
            environment_id=environment.id,
            payload={"name": secret_ref.name, "reason": str(exc)},
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Secret rotation failed") from exc
    await record_audit_event(
        db,
        action="secret.rotated",
        entity_type="secret_ref",
        entity_id=str(secret_ref.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"name": secret_ref.name, "provider_key": secret_ref.provider_key},
    )
    await db.commit()
    await db.refresh(secret_ref)
    return secret_ref


async def revoke_secret_ref(
    db: AsyncSession,
    *,
    secret_ref: SecretRef,
    project: Project,
    environment: Environment,
    actor: User,
) -> None:
    secret_ref.status = SecretStatus.REVOKED
    touch_updated_at(secret_ref)
    await record_audit_event(
        db,
        action="secret.revoked",
        entity_type="secret_ref",
        entity_id=str(secret_ref.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"name": secret_ref.name, "provider_key": secret_ref.provider_key},
    )
    await db.commit()


async def create_namespace_metadata(
    db: AsyncSession,
    *,
    environment: Environment,
    project: Project,
    actor: User,
    name: str,
) -> DataNamespace:
    namespace_name = validate_identifier(name, "Namespace name")
    existing = (
        await db.execute(
            select(DataNamespace).where(
                DataNamespace.environment_id == environment.id,
                DataNamespace.name == namespace_name,
            )
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Namespace already exists")

    namespace = DataNamespace(
        environment_id=environment.id,
        name=namespace_name,
        physical_schema=build_physical_schema(project.slug, environment.slug, namespace_name),
    )
    db.add(namespace)
    await db.flush()
    await record_audit_event(
        db,
        action="namespace.created",
        entity_type="data_namespace",
        entity_id=str(namespace.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"name": namespace.name, "physical_schema": namespace.physical_schema},
    )
    await db.commit()
    await db.refresh(namespace)
    return namespace


async def create_table_metadata(
    db: AsyncSession,
    *,
    namespace: DataNamespace,
    project: Project,
    environment: Environment,
    actor: User,
    table_name: str,
    columns: list[dict],
    policy_mode: PolicyMode,
    owner_column: str | None,
) -> TableDefinition:
    normalized_table = validate_identifier(table_name, "Table name")
    existing = (
        await db.execute(
            select(TableDefinition).where(
                TableDefinition.namespace_id == namespace.id,
                TableDefinition.table_name == normalized_table,
            )
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Table already exists")

    provider_entry = TableDefinition(
        namespace_id=namespace.id,
        table_name=normalized_table,
        columns_json=columns,
        policy_mode=policy_mode,
        owner_column=owner_column,
    )
    db.add(provider_entry)
    await db.flush()
    migration_status = (
        MigrationStatus.APPLIED
        if environment.stage == EnvironmentStage.DEVELOPMENT
        else MigrationStatus.PENDING
    )
    if migration_status == MigrationStatus.PENDING:
        provider_entry.status = "pending_migration"
    db.add(
        SchemaMigration(
            environment_id=environment.id,
            namespace_id=namespace.id,
            table_definition_id=provider_entry.id,
            version=f"{provider_entry.id:04d}",
            status=migration_status,
            applied_sql=f"create table {normalized_table}",
        )
    )
    await record_audit_event(
        db,
        action="table.created",
        entity_type="table_definition",
        entity_id=str(provider_entry.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"table_name": normalized_table, "policy_mode": policy_mode.value},
    )
    await db.commit()
    await db.refresh(provider_entry)
    return provider_entry


async def apply_schema_migration(
    db: AsyncSession,
    *,
    migration: SchemaMigration,
    environment: Environment,
    project: Project,
    actor: User,
) -> SchemaMigration:
    if migration.environment_id != environment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")
    if migration.status == MigrationStatus.APPLIED:
        return migration

    migration.status = MigrationStatus.APPLIED
    definition = await db.get(TableDefinition, migration.table_definition_id)
    if definition is not None:
        definition.status = "active"
        touch_updated_at(definition)
    touch_updated_at(migration)
    await db.flush()
    await record_audit_event(
        db,
        action="migration.applied",
        entity_type="schema_migration",
        entity_id=str(migration.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"version": migration.version},
    )
    await db.commit()
    await db.refresh(migration)
    return migration


async def rollback_schema_migration(
    db: AsyncSession,
    *,
    migration: SchemaMigration,
    environment: Environment,
    project: Project,
    actor: User,
) -> SchemaMigration:
    if migration.environment_id != environment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")
    if migration.status == MigrationStatus.PENDING:
        return migration

    migration.status = MigrationStatus.PENDING
    definition = await db.get(TableDefinition, migration.table_definition_id)
    if definition is not None:
        definition.status = "pending_migration"
        touch_updated_at(definition)
    touch_updated_at(migration)
    await db.flush()
    await record_audit_event(
        db,
        action="migration.rollback_requested",
        entity_type="schema_migration",
        entity_id=str(migration.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"version": migration.version, "rollback_sql": f"-- rollback for migration {migration.version}"},
    )
    await db.commit()
    await db.refresh(migration)
    return migration


def touch_updated_at(model: object) -> None:
    if hasattr(model, "updated_at"):
        setattr(model, "updated_at", datetime.now(timezone.utc))


async def create_switchover_plan(
    db: AsyncSession,
    *,
    binding: CapabilityBinding,
    target_provider_key: str,
    actor: User,
    project: Project,
    environment: Environment,
    strategy: str,
) -> SwitchoverPlan:
    target_provider = (
        await db.execute(
            select(ProviderCatalogEntry).where(
                ProviderCatalogEntry.capability_type_id == binding.capability_type_id,
                ProviderCatalogEntry.provider_key == target_provider_key,
            )
        )
    ).scalars().first()
    if target_provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target provider not found")
    capability_type = await db.get(CapabilityType, binding.capability_type_id)
    if capability_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found")
    capability_key = CapabilityKey(capability_type.key)
    current_profile, target_profile = _load_provider_profiles(
        capability_key=capability_key,
        current_provider_key=(await db.get(ProviderCatalogEntry, binding.provider_catalog_entry_id)).provider_key,  # type: ignore[union-attr]
        target_provider_key=target_provider_key,
    )
    _validate_switchover_profiles(
        capability_key=capability_key,
        current_profile=current_profile,
        target_profile=target_profile,
    )
    target_adapter = provider_registry.resolve(capability_key, target_provider_key)
    target_health = await target_adapter.health()
    if not target_health.ready:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target provider is not ready: {target_health.detail}",
        )

    switchover = SwitchoverPlan(
        capability_binding_id=binding.id,
        target_provider_catalog_entry_id=target_provider.id,
        strategy=strategy,
        status=SwitchoverStatus.PENDING,
        execution_detail="plan created; awaiting execution",
        requested_by_user_id=actor.id,
    )
    db.add(switchover)
    await db.flush()
    await record_audit_event(
        db,
        action="binding.switchover_planned",
        entity_type="switchover_plan",
        entity_id=str(switchover.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"binding_id": binding.id, "target_provider_key": target_provider_key, "strategy": strategy},
    )
    await db.commit()
    await db.refresh(switchover)
    return switchover


async def execute_switchover_plan(
    db: AsyncSession,
    *,
    switchover: SwitchoverPlan,
    actor: User,
    project: Project,
    environment: Environment,
) -> SwitchoverPlan:
    binding = await db.get(CapabilityBinding, switchover.capability_binding_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    if switchover.status != SwitchoverStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Switchover is not pending")

    previous_provider_catalog_entry_id = binding.provider_catalog_entry_id
    switchover.status = SwitchoverStatus.RUNNING
    switchover.execution_detail = "checkpoint:preflight_ok"
    await db.flush()
    try:
        binding.provider_catalog_entry_id = switchover.target_provider_catalog_entry_id
        binding.status = BindingStatus.ACTIVE
        binding.readiness_detail = "switchover executed"
        binding.last_transition_actor_user_id = actor.id
        binding.last_transition_reason = "switchover_executed"
        binding.last_transition_at = datetime.now(timezone.utc)
        touch_updated_at(binding)
        switchover.status = SwitchoverStatus.COMPLETED
        switchover.execution_detail = "switchover executed successfully"
        switchover.completed_at = datetime.now(timezone.utc)
        await db.flush()
    except Exception as exc:
        binding.provider_catalog_entry_id = previous_provider_catalog_entry_id
        binding.status = BindingStatus.ACTIVE
        binding.readiness_detail = "switchover rollback to previous provider"
        binding.last_transition_actor_user_id = actor.id
        binding.last_transition_reason = "switchover_rollback"
        binding.last_transition_at = datetime.now(timezone.utc)
        touch_updated_at(binding)
        switchover.status = SwitchoverStatus.FAILED
        switchover.execution_detail = f"rollback_complete:{exc}"
        switchover.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await record_audit_event(
            db,
            action="binding.switchover_failed",
            entity_type="switchover_plan",
            entity_id=str(switchover.id),
            actor_user_id=actor.id,
            tenant_id=project.tenant_id,
            project_id=project.id,
            environment_id=environment.id,
            payload={"binding_id": binding.id, "rollback_provider_catalog_entry_id": previous_provider_catalog_entry_id},
        )
        await db.commit()
        await db.refresh(switchover)
        return switchover
    await record_audit_event(
        db,
        action="binding.switchover_executed",
        entity_type="switchover_plan",
        entity_id=str(switchover.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"binding_id": binding.id, "strategy": switchover.strategy},
    )
    await db.commit()
    await db.refresh(switchover)
    return switchover


async def create_binding_version(
    db: AsyncSession,
    *,
    environment: Environment,
    capability: CapabilityType,
    provider: ProviderCatalogEntry,
    actor: User,
    project: Project,
    config_json: dict,
    region: str | None,
    secret_ref_ids: list[int],
) -> CapabilityBinding:
    if secret_ref_ids:
        secret_scope_rows = (
            await db.execute(select(SecretRef).where(SecretRef.id.in_(secret_ref_ids)))
        ).scalars().all()
        secret_scope_by_id = {item.id: item for item in secret_scope_rows}
        out_of_boundary = [
            secret_id
            for secret_id in secret_ref_ids
            if secret_id not in secret_scope_by_id or secret_scope_by_id[secret_id].environment_id != environment.id
        ]
        if out_of_boundary:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant boundary violation: one or more secrets are outside the target environment",
            )

    current_active = (
        await db.execute(
            select(CapabilityBinding).where(
                CapabilityBinding.environment_id == environment.id,
                CapabilityBinding.capability_type_id == capability.id,
                CapabilityBinding.status == BindingStatus.ACTIVE,
            )
        )
    ).scalars().first()
    binding = CapabilityBinding(
        environment_id=environment.id,
        capability_type_id=capability.id,
        provider_catalog_entry_id=provider.id,
        config_json=config_json,
        status=BindingStatus.PENDING_VALIDATION,
        region=region,
        supersedes_binding_id=current_active.id if current_active else None,
        last_transition_actor_user_id=actor.id,
        last_transition_reason="binding_version_created",
        last_transition_at=datetime.now(timezone.utc),
    )
    db.add(binding)
    await db.flush()

    for secret_ref_id in secret_ref_ids:
        db.add(BindingSecretRef(binding_id=binding.id, secret_ref_id=secret_ref_id))

    required_secret_kinds = provider.metadata_json.get("required_secret_kinds", [])
    linked_secrets = (
        await db.execute(
            select(SecretRef)
            .join(BindingSecretRef, BindingSecretRef.secret_ref_id == SecretRef.id)
            .where(BindingSecretRef.binding_id == binding.id, SecretRef.status == SecretStatus.ACTIVE)
        )
    ).scalars().all()
    linked_secret_kinds = {item.secret_kind for item in linked_secrets}
    missing_secret_kinds = sorted(set(required_secret_kinds) - linked_secret_kinds)

    supported_regions = provider.metadata_json.get("supported_regions", ["global"])
    region_valid = region is None or "global" in supported_regions or region in supported_regions
    if missing_secret_kinds or not region_valid:
        binding.status = BindingStatus.FAILED
        details = []
        if missing_secret_kinds:
            details.append(f"missing secrets: {', '.join(missing_secret_kinds)}")
        if not region_valid:
            details.append(f"unsupported region '{region}'")
        binding.readiness_detail = "; ".join(details)
        environment.readiness_state = ReadinessState.DEGRADED
        environment.status = EnvironmentStatus.DEGRADED
        environment.readiness_detail = binding.readiness_detail
    else:
        binding.status = BindingStatus.ACTIVE
        binding.readiness_detail = "validated"
        if current_active is not None:
            current_active.status = BindingStatus.DEPRECATED
            current_active.last_transition_actor_user_id = actor.id
            current_active.last_transition_reason = "superseded_by_new_active_binding"
            current_active.last_transition_at = datetime.now(timezone.utc)
            touch_updated_at(current_active)
        environment.readiness_state = ReadinessState.READY
        environment.status = EnvironmentStatus.ACTIVE
        environment.readiness_detail = "bindings validated"

    environment.last_validated_at = datetime.now(timezone.utc)
    touch_updated_at(binding)
    await db.flush()
    await record_audit_event(
        db,
        action="binding.version_created",
        entity_type="capability_binding",
        entity_id=str(binding.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"capability_key": capability.key, "provider_key": provider.provider_key, "status": binding.status.value},
    )
    await db.commit()
    await db.refresh(binding)
    return binding


async def _list_bindings_using_secret(db: AsyncSession, *, secret_ref_id: int) -> list[int]:
    return (
        await db.execute(
            select(BindingSecretRef.binding_id).where(BindingSecretRef.secret_ref_id == secret_ref_id)
        )
    ).scalars().all()


async def set_binding_status(
    db: AsyncSession,
    *,
    binding: CapabilityBinding,
    status_value: BindingStatus,
    reason: str | None,
    actor: User,
    project: Project,
    environment: Environment,
) -> CapabilityBinding:
    _assert_binding_transition_is_legal(
        binding_id=binding.id,
        current_status=binding.status,
        target_status=status_value,
    )
    if status_value == BindingStatus.ACTIVE:
        active_conflict = (
            await db.execute(
                select(CapabilityBinding).where(
                    CapabilityBinding.environment_id == binding.environment_id,
                    CapabilityBinding.capability_type_id == binding.capability_type_id,
                    CapabilityBinding.status == BindingStatus.ACTIVE,
                    CapabilityBinding.id != binding.id,
                )
            )
        ).scalars().first()
        if active_conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_active_binding_conflict_payload(
                    binding_id=binding.id,
                    conflicting_binding_id=active_conflict.id,
                ),
            )

    binding.status = status_value
    binding.last_transition_actor_user_id = actor.id
    binding.last_transition_reason = reason or "manual_status_update"
    binding.last_transition_at = datetime.now(timezone.utc)
    touch_updated_at(binding)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if _is_active_binding_uniqueness_error(exc):
            conflicting_active = (
                await db.execute(
                    select(CapabilityBinding).where(
                        CapabilityBinding.environment_id == binding.environment_id,
                        CapabilityBinding.capability_type_id == binding.capability_type_id,
                        CapabilityBinding.status == BindingStatus.ACTIVE,
                        CapabilityBinding.id != binding.id,
                    )
                )
            ).scalars().first()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_active_binding_conflict_payload(
                    binding_id=binding.id,
                    conflicting_binding_id=conflicting_active.id if conflicting_active is not None else binding.id,
                ),
            ) from exc
        raise
    await record_audit_event(
        db,
        action="binding.status_updated",
        entity_type="capability_binding",
        entity_id=str(binding.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"status": status_value.value, "reason": binding.last_transition_reason},
    )
    await db.commit()
    await db.refresh(binding)
    return binding


async def build_capability_health_report(
    db: AsyncSession,
    *,
    environment: Environment,
    project: Project,
) -> tuple[
    list[tuple[CapabilityBinding, CapabilityType, ProviderCatalogEntry]],
    list[dict[str, object]],
    list[str],
]:
    if not provider_registry.registered_profiles():
        from src.postbase.platform.bootstrap import bootstrap_postbase_runtime
        bootstrap_postbase_runtime()

    binding_rows = (
        await db.execute(
            select(CapabilityBinding, CapabilityType, ProviderCatalogEntry)
            .join(CapabilityType, CapabilityBinding.capability_type_id == CapabilityType.id)
            .join(ProviderCatalogEntry, CapabilityBinding.provider_catalog_entry_id == ProviderCatalogEntry.id)
            .where(CapabilityBinding.environment_id == environment.id)
        )
    ).all()

    provider_health: list[dict[str, object]] = []
    degraded_capabilities: list[str] = []
    for binding, capability_type, provider_entry in binding_rows:
        if binding.status != BindingStatus.ACTIVE:
            health_payload = {
                "capability_key": capability_type.key,
                "provider_key": provider_entry.provider_key,
                "adapter_version": provider_entry.adapter_version,
                "ready": False,
                "detail": f"binding is {binding.status.value}",
            }
            provider_health.append(health_payload)
            degraded_capabilities.append(capability_type.key)
            continue
        resolved = await resolve_active_binding(
            db,
            environment_id=environment.id,
            project_id=project.id,
            capability=CapabilityKey(capability_type.key),
        )
        adapter = provider_registry.resolve(resolved.capability, resolved.provider_key)
        health = await adapter.health()
        provider_health.append(
            {
                "capability_key": capability_type.key,
                "provider_key": provider_entry.provider_key,
                "adapter_version": provider_entry.adapter_version,
                "ready": health.ready,
                "detail": health.detail,
            }
        )
        if not health.ready:
            degraded_capabilities.append(capability_type.key)
    return binding_rows, provider_health, sorted(set(degraded_capabilities))


async def get_project_usage_meters(
    db: AsyncSession,
    *,
    project: Project,
) -> list[UsageMeter]:
    environment_ids = [
        item.id
        for item in (
            await db.execute(select(Environment).where(Environment.project_id == project.id))
        ).scalars().all()
    ]
    if not environment_ids:
        return []
    return (
        await db.execute(
            select(UsageMeter)
            .where(UsageMeter.environment_id.in_(environment_ids))
            .order_by(UsageMeter.capability_key.asc(), UsageMeter.metric_key.asc())
        )
    ).scalars().all()


async def build_project_overview(
    db: AsyncSession,
    *,
    project: Project,
) -> dict[str, object]:
    environments = (
        await db.execute(select(Environment).where(Environment.project_id == project.id))
    ).scalars().all()
    environment_ids = [environment.id for environment in environments]
    bindings = []
    secrets = []
    keys = []
    usage_meters = []
    audit_logs = []
    switchovers = []
    migrations = []
    if environment_ids:
        bindings = (
            await db.execute(select(CapabilityBinding).where(CapabilityBinding.environment_id.in_(environment_ids)))
        ).scalars().all()
        secrets = (
            await db.execute(select(SecretRef).where(SecretRef.environment_id.in_(environment_ids)))
        ).scalars().all()
        keys = (
            await db.execute(select(EnvironmentApiKey).where(EnvironmentApiKey.environment_id.in_(environment_ids)))
        ).scalars().all()
        usage_meters = (
            await db.execute(select(UsageMeter).where(UsageMeter.environment_id.in_(environment_ids)))
        ).scalars().all()
        switchovers = (
            await db.execute(
                select(SwitchoverPlan)
                .join(CapabilityBinding, CapabilityBinding.id == SwitchoverPlan.capability_binding_id)
                .where(CapabilityBinding.environment_id.in_(environment_ids))
            )
        ).scalars().all()
        migrations = (
            await db.execute(select(SchemaMigration).where(SchemaMigration.environment_id.in_(environment_ids)))
        ).scalars().all()
        last_day = datetime.now(timezone.utc).replace(microsecond=0)
        audit_logs = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.project_id == project.id,
                    AuditLog.created_at >= last_day.replace(hour=0, minute=0, second=0),
                )
            )
        ).scalars().all()

    health_by_environment: dict[int, dict[str, int]] = {
        environment.id: {"active": 0, "degraded": 0}
        for environment in environments
    }
    for binding in bindings:
        bucket = health_by_environment.setdefault(binding.environment_id, {"active": 0, "degraded": 0})
        if binding.status == BindingStatus.ACTIVE:
            bucket["active"] += 1
        else:
            bucket["degraded"] += 1

    environment_rows: list[dict[str, object]] = []
    for environment in environments:
        environment_secret_count = sum(1 for item in secrets if item.environment_id == environment.id and item.status == SecretStatus.ACTIVE)
        environment_key_count = sum(1 for item in keys if item.environment_id == environment.id and item.is_active)
        environment_usage = sum(item.value for item in usage_meters if item.environment_id == environment.id)
        environment_audit_count = sum(1 for item in audit_logs if item.environment_id == environment.id)
        environment_switchovers = sum(
            1
            for item in switchovers
            if (
                next(
                    (
                        binding.environment_id
                        for binding in bindings
                        if binding.id == item.capability_binding_id
                    ),
                    None,
                )
                == environment.id
            )
        )
        pending_migrations = sum(
            1
            for item in migrations
            if item.environment_id == environment.id and item.status == MigrationStatus.PENDING
        )
        environment_health = health_by_environment[environment.id]
        environment_rows.append(
            {
                "environment_id": encode_id(environment.id),
                "stage": environment.stage,
                "status": environment.status,
                "readiness_state": environment.readiness_state,
                "readiness_detail": environment.readiness_detail,
                "active_bindings": environment_health["active"],
                "degraded_bindings": environment_health["degraded"],
                "recent_switchovers": environment_switchovers,
                "pending_migrations": pending_migrations,
                "secret_count": environment_secret_count,
                "key_count": environment_key_count,
                "usage_points_total": environment_usage,
                "recent_audit_events": environment_audit_count,
            }
        )

    return {
        "project_id": encode_id(project.id),
        "environment_count": len(environments),
        "active_environment_count": sum(1 for environment in environments if environment.is_active),
        "active_bindings": sum(item["active"] for item in health_by_environment.values()),
        "degraded_bindings": sum(item["degraded"] for item in health_by_environment.values()),
        "secret_count": sum(1 for item in secrets if item.status == SecretStatus.ACTIVE),
        "usage_points_total": sum(item.value for item in usage_meters),
        "recent_audit_events": len(audit_logs),
        "environments": environment_rows,
    }


def _load_provider_profiles(
    *,
    capability_key: CapabilityKey,
    current_provider_key: str,
    target_provider_key: str,
) -> tuple[CapabilityProfile, CapabilityProfile]:
    if not provider_registry.registered_profiles():
        from src.postbase.platform.bootstrap import bootstrap_postbase_runtime
        bootstrap_postbase_runtime()
    current_profile = provider_registry.resolve(capability_key, current_provider_key).profile()
    target_profile = provider_registry.resolve(capability_key, target_provider_key).profile()
    return current_profile, target_profile


def _validate_switchover_profiles(
    *,
    capability_key: CapabilityKey,
    current_profile: CapabilityProfile,
    target_profile: CapabilityProfile,
) -> None:
    required_operations = REQUIRED_OPERATIONS[capability_key]
    target_supported = set(target_profile.supported_operations)
    if not required_operations.issubset(target_supported):
        missing = sorted(required_operations - target_supported)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Provider '{target_profile.provider_key}' is missing required "
                f"{capability_key.value} operations: {', '.join(missing)}"
            ),
        )
    current_supported = set(current_profile.supported_operations)
    if not current_supported.issubset(target_supported):
        missing = sorted(current_supported - target_supported)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Provider '{target_profile.provider_key}' cannot fully replace "
                f"'{current_profile.provider_key}'. Missing: {', '.join(missing)}"
            ),
        )
