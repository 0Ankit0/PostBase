from __future__ import annotations

from datetime import timezone, datetime
from typing import Any

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
    SchemaMigrationExecution,
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
from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider


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
ALLOWED_RETIREMENT_STRATEGIES = {"immediate", "deferred", "manual"}
SWITCHOVER_PHASE_ORDER = [
    "preflight",
    "stage_target",
    "validate_cutover",
    "retire_old_binding",
    "completed",
]
LEGAL_ENVIRONMENT_STATUS_TRANSITIONS: dict[EnvironmentStatus, set[EnvironmentStatus]] = {
    EnvironmentStatus.ACTIVE: {EnvironmentStatus.DEGRADED, EnvironmentStatus.INACTIVE},
    EnvironmentStatus.DEGRADED: {EnvironmentStatus.ACTIVE, EnvironmentStatus.INACTIVE},
    EnvironmentStatus.INACTIVE: {EnvironmentStatus.ACTIVE},
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


async def set_project_lifecycle_state(
    db: AsyncSession,
    *,
    project: Project,
    actor: User,
    is_active: bool,
) -> Project:
    await require_project_access(db, project=project, user_id=actor.id, min_role=TenantRole.ADMIN)
    project.is_active = is_active
    touch_updated_at(project)
    await db.flush()
    await record_audit_event(
        db,
        action="project.lifecycle_updated",
        entity_type="project",
        entity_id=str(project.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        payload={"is_active": is_active, "outcome": "allowed"},
    )
    await db.commit()
    await db.refresh(project)
    return project


async def set_environment_lifecycle_state(
    db: AsyncSession,
    *,
    environment: Environment,
    project: Project,
    actor: User,
    status_value: EnvironmentStatus | None,
    is_active: bool | None,
    reason: str | None,
) -> Environment:
    await require_project_access(db, project=project, user_id=actor.id, min_role=TenantRole.ADMIN)
    current_status = environment.status
    target_status = status_value or current_status
    if current_status != target_status and target_status not in LEGAL_ENVIRONMENT_STATUS_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "environment_invalid_status_transition",
                "message": "invalid_status_transition",
                "environment_id": encode_id(environment.id),
                "from_status": current_status.value,
                "to_status": target_status.value,
            },
        )
    if is_active is False:
        target_status = EnvironmentStatus.INACTIVE
    if is_active is None:
        is_active = environment.is_active
    environment.is_active = is_active
    environment.status = target_status
    environment.readiness_detail = reason or environment.readiness_detail
    touch_updated_at(environment)
    await db.flush()
    await record_audit_event(
        db,
        action="environment.lifecycle_updated",
        entity_type="environment",
        entity_id=str(environment.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={
            "status": environment.status.value,
            "is_active": environment.is_active,
            "reason": reason or "",
            "outcome": "allowed",
        },
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
                SecretRef.is_active_version == True,
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
        version=1,
        is_active_version=True,
        encrypted_value=secret_store.encrypt(secret_value),
        value_hash=hash_secret(secret_value),
        last_four=secret_value[-4:] if secret_value else "",
        rotated_at=datetime.now(timezone.utc),
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
    impacted_bindings = await _list_bindings_using_secret_family(
        db,
        environment_id=secret_ref.environment_id,
        name=secret_ref.name,
        provider_key=secret_ref.provider_key,
        secret_kind=secret_ref.secret_kind,
    )
    if not impacted_bindings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret is not linked to any binding; link before rotation to avoid blind rotation",
        )

    secret_store = DbEncryptedSecretStore(settings.POSTBASE_SECRET_ENCRYPTION_KEY)
    current_active = (
        await db.execute(
            select(SecretRef)
            .where(
                SecretRef.environment_id == secret_ref.environment_id,
                SecretRef.name == secret_ref.name,
                SecretRef.provider_key == secret_ref.provider_key,
                SecretRef.secret_kind == secret_ref.secret_kind,
                SecretRef.is_active_version == True,
            )
            .order_by(SecretRef.version.desc())
        )
    ).scalars().first()
    next_version = (current_active.version if current_active is not None else secret_ref.version) + 1
    rotated_secret = SecretRef(
        environment_id=secret_ref.environment_id,
        name=secret_ref.name,
        provider_key=secret_ref.provider_key,
        secret_kind=secret_ref.secret_kind,
        version=next_version,
        is_active_version=True,
        status=SecretStatus.ACTIVE,
        encrypted_value=secret_store.encrypt(secret_value),
        value_hash=hash_secret(secret_value),
        last_four=secret_value[-4:] if secret_value else "",
        rotated_at=datetime.now(timezone.utc),
    )
    if current_active is not None:
        current_active.is_active_version = False
        touch_updated_at(current_active)
    secret_ref.is_active_version = False
    touch_updated_at(secret_ref)
    db.add(rotated_secret)
    try:
        await db.flush()
    except Exception as exc:
        await db.rollback()
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
    await db.refresh(rotated_secret)
    return rotated_secret


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
        else MigrationStatus.QUEUED
    )
    if migration_status in {MigrationStatus.QUEUED, MigrationStatus.PENDING}:
        provider_entry.status = "pending_migration"
    db.add(
        SchemaMigration(
            environment_id=environment.id,
            namespace_id=namespace.id,
            table_definition_id=provider_entry.id,
            version=f"{provider_entry.id:04d}",
            status=migration_status,
            reconciliation_status="in_sync" if migration_status == MigrationStatus.APPLIED else "pending_apply",
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
    if migration.status == MigrationStatus.CANCELED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Canceled migration cannot be applied")

    execution = await _start_migration_execution(db, migration=migration, environment=environment)
    definition = await db.get(TableDefinition, migration.table_definition_id)
    namespace = await db.get(DataNamespace, migration.namespace_id)
    provider = PostgresNativeDataProvider()
    try:
        migration.status = MigrationStatus.PENDING
        touch_updated_at(migration)
        await db.flush()

        if definition is not None and namespace is not None:
            await provider.create_namespace(db, namespace)
            await provider.create_table(db, namespace, definition)
            definition.status = "active"
            touch_updated_at(definition)

        migration.status = MigrationStatus.APPLIED
        migration.reconciliation_status = "in_sync"
        migration.drift_severity = "none"
        migration.drift_entities_json = []
        migration.reconcile_error_text = ""
        migration.last_reconciled_at = datetime.now(timezone.utc)
        touch_updated_at(migration)
        await _finish_migration_execution(db, execution=execution, status=MigrationStatus.APPLIED)
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
    except Exception as exc:
        await db.rollback()
        migration = await db.get(SchemaMigration, migration.id)
        if migration is None:
            raise
        migration.status = MigrationStatus.FAILED
        migration.reconciliation_status = "drifted"
        migration.drift_severity = "critical"
        migration.drift_entities_json = [f"migration:{migration.id}"]
        migration.reconcile_error_text = str(exc)
        migration.last_reconciled_at = datetime.now(timezone.utc)
        touch_updated_at(migration)
        definition = await db.get(TableDefinition, migration.table_definition_id)
        if definition is not None:
            definition.status = "pending_migration"
            touch_updated_at(definition)
        execution = await db.get(SchemaMigrationExecution, execution.id)
        if execution is None:
            execution = await _start_migration_execution(db, migration=migration, environment=environment)
        await _finish_migration_execution(db, execution=execution, status=MigrationStatus.FAILED, error_text=str(exc))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Migration apply failed: {exc}") from exc

    await db.refresh(migration)
    return migration


async def retry_schema_migration(
    db: AsyncSession,
    *,
    migration: SchemaMigration,
    environment: Environment,
    project: Project,
    actor: User,
) -> SchemaMigration:
    if migration.environment_id != environment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")
    if migration.status != MigrationStatus.FAILED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only failed migrations can be retried")

    migration.status = MigrationStatus.PENDING
    touch_updated_at(migration)
    await db.flush()
    await db.commit()
    await db.refresh(migration)
    return await apply_schema_migration(
        db,
        migration=migration,
        environment=environment,
        project=project,
        actor=actor,
    )


async def cancel_schema_migration(
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Applied migration cannot be canceled")
    if migration.status == MigrationStatus.CANCELED:
        return migration

    migration.status = MigrationStatus.CANCELED
    migration.reconciliation_status = "canceled"
    migration.drift_severity = "none"
    migration.drift_entities_json = []
    migration.reconcile_error_text = ""
    migration.last_reconciled_at = datetime.now(timezone.utc)
    definition = await db.get(TableDefinition, migration.table_definition_id)
    if definition is not None:
        definition.status = "canceled_migration"
        touch_updated_at(definition)
    touch_updated_at(migration)
    await db.flush()
    await record_audit_event(
        db,
        action="migration.canceled",
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


async def _start_migration_execution(
    db: AsyncSession,
    *,
    migration: SchemaMigration,
    environment: Environment,
) -> SchemaMigrationExecution:
    execution = SchemaMigrationExecution(
        migration_id=migration.id,
        environment_id=environment.id,
        status=MigrationStatus.PENDING,
    )
    db.add(execution)
    await db.flush()
    return execution


async def _finish_migration_execution(
    db: AsyncSession,
    *,
    execution: SchemaMigrationExecution,
    status: MigrationStatus,
    error_text: str = "",
) -> None:
    execution.status = status
    execution.error_text = error_text
    execution.finished_at = datetime.now(timezone.utc)
    await db.flush()


def _derive_drift_severity(affected_entities: list[str]) -> str:
    if not affected_entities:
        return "none"
    if any(entity.startswith("table:") for entity in affected_entities):
        return "critical"
    if any(entity.startswith("namespace:") for entity in affected_entities):
        return "high"
    return "medium"


async def detect_migration_drift(
    db: AsyncSession,
    *,
    migration: SchemaMigration,
) -> tuple[str, str, list[str]]:
    if migration.status in {MigrationStatus.QUEUED, MigrationStatus.PENDING}:
        return "pending_apply", "none", []
    if migration.status == MigrationStatus.CANCELED:
        return "canceled", "none", []
    if migration.status == MigrationStatus.FAILED:
        return "drifted", "critical", [f"migration:{migration.id}"]

    namespace = await db.get(DataNamespace, migration.namespace_id)
    definition = await db.get(TableDefinition, migration.table_definition_id) if migration.table_definition_id else None
    affected_entities: list[str] = []
    if namespace is None:
        affected_entities.append(f"namespace:{migration.namespace_id}")
    if migration.table_definition_id is not None and definition is None:
        affected_entities.append(f"table_definition:{migration.table_definition_id}")

    if namespace is not None and definition is not None:
        provider = PostgresNativeDataProvider()
        table_exists = await provider.table_exists(db, namespace, definition.table_name)
        if not table_exists:
            affected_entities.append(f"table:{namespace.physical_schema}.{definition.table_name}")
        else:
            actual_columns = await provider.list_table_columns(db, namespace, definition.table_name)
            expected_columns = {column["name"] for column in definition.columns_json if "name" in column}
            expected_columns.add("id")
            missing_columns = sorted(expected_columns - actual_columns)
            affected_entities.extend(
                f"column:{namespace.physical_schema}.{definition.table_name}.{column_name}"
                for column_name in missing_columns
            )

    severity = _derive_drift_severity(affected_entities)
    return ("in_sync", severity, []) if not affected_entities else ("drifted", severity, affected_entities)


async def refresh_migration_reconciliation_state(
    db: AsyncSession,
    *,
    migration: SchemaMigration,
) -> SchemaMigration:
    reconciliation_status, drift_severity, affected_entities = await detect_migration_drift(db, migration=migration)
    migration.reconciliation_status = reconciliation_status
    migration.drift_severity = drift_severity
    migration.drift_entities_json = affected_entities
    migration.reconcile_error_text = ""
    migration.last_reconciled_at = datetime.now(timezone.utc)
    touch_updated_at(migration)
    await db.flush()
    return migration


async def execute_migration_reconciliation(
    db: AsyncSession,
    *,
    migration: SchemaMigration,
    max_retries: int = 3,
) -> SchemaMigration:
    migration = await refresh_migration_reconciliation_state(db, migration=migration)
    if migration.reconciliation_status == "in_sync":
        return migration
    if migration.status != MigrationStatus.APPLIED:
        return migration

    if migration.reconcile_attempt_count >= max_retries:
        migration.reconcile_error_text = "reconciliation retry budget exhausted"
        touch_updated_at(migration)
        await db.flush()
        return migration

    migration.reconcile_attempt_count += 1
    touch_updated_at(migration)
    await db.flush()

    namespace = await db.get(DataNamespace, migration.namespace_id)
    definition = await db.get(TableDefinition, migration.table_definition_id) if migration.table_definition_id else None
    if namespace is None or definition is None:
        migration.reconcile_error_text = "metadata entities required for reconciliation are missing"
        migration.reconciliation_status = "drifted"
        migration.last_reconciled_at = datetime.now(timezone.utc)
        touch_updated_at(migration)
        await db.flush()
        return migration

    provider = PostgresNativeDataProvider()
    try:
        await provider.create_namespace(db, namespace)
        await provider.create_table(db, namespace, definition)
        migration.reconcile_error_text = ""
    except Exception as exc:
        migration.reconcile_error_text = str(exc)
        migration.reconciliation_status = "drifted"
        migration.last_reconciled_at = datetime.now(timezone.utc)
        touch_updated_at(migration)
        await db.flush()
        return migration

    return await refresh_migration_reconciliation_state(db, migration=migration)


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
    retirement_strategy: str,
) -> SwitchoverPlan:
    if retirement_strategy not in ALLOWED_RETIREMENT_STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"retirement_strategy must be one of {sorted(ALLOWED_RETIREMENT_STRATEGIES)}",
        )
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
    preflight_report = await _build_switchover_preflight_report(
        db,
        binding=binding,
        target_provider=target_provider,
        environment=environment,
    )
    if not _preflight_is_ready(preflight_report):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "switchover_preflight_failed",
                "message": "switchover_preflight_failed",
                "preflight": preflight_report,
            },
        )

    switchover = SwitchoverPlan(
        capability_binding_id=binding.id,
        target_provider_catalog_entry_id=target_provider.id,
        strategy=strategy,
        retirement_strategy=retirement_strategy,
        status=SwitchoverStatus.PENDING,
        execution_detail="phase:preflight; checkpoint:validated",
        execution_state_json={
            "phase": "preflight",
            "completed_phases": [],
            "preflight_report": preflight_report,
            "rollback_checkpoint": {},
            "retirement": {
                "strategy": retirement_strategy,
                "status": "pending",
            },
        },
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
        payload={
            "binding_id": binding.id,
            "target_provider_key": target_provider_key,
            "strategy": strategy,
            "retirement_strategy": retirement_strategy,
            "preflight_report": preflight_report,
        },
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
    if switchover.status == SwitchoverStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Switchover is already completed")
    if switchover.status not in {SwitchoverStatus.PENDING, SwitchoverStatus.RUNNING, SwitchoverStatus.FAILED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Switchover cannot be resumed")

    execution_state: dict[str, Any] = dict(switchover.execution_state_json or {})
    execution_state.setdefault("phase", "preflight")
    execution_state.setdefault("completed_phases", [])
    execution_state.setdefault("rollback_checkpoint", {})
    execution_state.setdefault(
        "retirement",
        {"strategy": switchover.retirement_strategy, "status": "pending"},
    )
    completed_phases = set(execution_state["completed_phases"])

    rollback_checkpoint = execution_state["rollback_checkpoint"]
    if rollback_checkpoint.get("required") and rollback_checkpoint.get("previous_provider_catalog_entry_id") is not None:
        binding.provider_catalog_entry_id = rollback_checkpoint["previous_provider_catalog_entry_id"]
        binding.status = BindingStatus.ACTIVE
        binding.readiness_detail = "rollback checkpoint restored previous provider"
        binding.last_transition_actor_user_id = actor.id
        binding.last_transition_reason = "switchover_checkpoint_rollback"
        binding.last_transition_at = datetime.now(timezone.utc)
        touch_updated_at(binding)
        rollback_checkpoint["required"] = False
        execution_state["phase"] = "preflight"
        execution_state["completed_phases"] = [phase for phase in execution_state["completed_phases"] if phase != "stage_target"]
        switchover.execution_state_json = execution_state
        switchover.execution_detail = "checkpoint rollback restored; ready to resume"
        switchover.status = SwitchoverStatus.RUNNING
        await db.flush()

    switchover.status = SwitchoverStatus.RUNNING
    await db.flush()
    try:
        if "preflight" not in completed_phases:
            target_provider = await db.get(ProviderCatalogEntry, switchover.target_provider_catalog_entry_id)
            if target_provider is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target provider not found")
            preflight_report = await _build_switchover_preflight_report(
                db,
                binding=binding,
                target_provider=target_provider,
                environment=environment,
            )
            if not _preflight_is_ready(preflight_report):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "switchover_preflight_failed",
                        "message": "switchover_preflight_failed",
                        "preflight": preflight_report,
                    },
                )
            execution_state["preflight_report"] = preflight_report
            execution_state["phase"] = "preflight"
            execution_state["completed_phases"] = [*execution_state["completed_phases"], "preflight"]
            switchover.execution_state_json = execution_state
            switchover.execution_detail = "phase:preflight; checkpoint:validated"
            await db.flush()

        if "stage_target" not in set(execution_state["completed_phases"]):
            execution_state["rollback_checkpoint"] = {
                "required": True,
                "previous_provider_catalog_entry_id": binding.provider_catalog_entry_id,
            }
            binding.provider_catalog_entry_id = switchover.target_provider_catalog_entry_id
            binding.status = BindingStatus.PENDING_VALIDATION
            binding.readiness_detail = "cutover staged on target provider"
            binding.last_transition_actor_user_id = actor.id
            binding.last_transition_reason = "switchover_stage_target"
            binding.last_transition_at = datetime.now(timezone.utc)
            touch_updated_at(binding)
            execution_state["phase"] = "stage_target"
            execution_state["completed_phases"] = [*execution_state["completed_phases"], "stage_target"]
            switchover.execution_state_json = execution_state
            switchover.execution_detail = "phase:stage_target; checkpoint:rollback_ready"
            await db.flush()

        if "validate_cutover" not in set(execution_state["completed_phases"]):
            target_provider = await db.get(ProviderCatalogEntry, switchover.target_provider_catalog_entry_id)
            capability_type = await db.get(CapabilityType, binding.capability_type_id)
            if target_provider is None or capability_type is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target switchover references are missing")
            target_adapter = provider_registry.resolve(CapabilityKey(capability_type.key), target_provider.provider_key)
            target_health = await target_adapter.health()
            if not target_health.ready:
                raise RuntimeError(f"target provider health validation failed: {target_health.detail}")
            await _validate_binding_activation_prerequisites(db, binding=binding, provider=target_provider)
            binding.status = BindingStatus.ACTIVE
            binding.readiness_detail = "switchover target validated"
            binding.last_transition_actor_user_id = actor.id
            binding.last_transition_reason = "switchover_validate_cutover"
            binding.last_transition_at = datetime.now(timezone.utc)
            touch_updated_at(binding)
            execution_state["phase"] = "validate_cutover"
            execution_state["completed_phases"] = [*execution_state["completed_phases"], "validate_cutover"]
            switchover.execution_state_json = execution_state
            switchover.execution_detail = "phase:validate_cutover; checkpoint:active_on_target"
            await db.flush()

        retirement = execution_state["retirement"]
        retirement_strategy = retirement.get("strategy", switchover.retirement_strategy)
        if "retire_old_binding" not in set(execution_state["completed_phases"]):
            retirement_status = {
                "immediate": "retired",
                "deferred": "deferred",
                "manual": "manual_action_required",
            }.get(retirement_strategy, "manual_action_required")
            retirement["status"] = retirement_status
            execution_state["retirement"] = retirement
            execution_state["phase"] = "retire_old_binding"
            execution_state["completed_phases"] = [*execution_state["completed_phases"], "retire_old_binding"]
            switchover.execution_state_json = execution_state
            switchover.execution_detail = f"phase:retire_old_binding; strategy:{retirement_strategy}; status:{retirement_status}"
            await db.flush()

        execution_state["phase"] = "completed"
        execution_state["completed_phases"] = SWITCHOVER_PHASE_ORDER[:-1]
        execution_state["rollback_checkpoint"] = {
            "required": False,
            "previous_provider_catalog_entry_id": execution_state.get("rollback_checkpoint", {}).get("previous_provider_catalog_entry_id"),
        }
        switchover.execution_state_json = execution_state
        switchover.status = SwitchoverStatus.COMPLETED
        switchover.execution_detail = "switchover executed successfully with staged checkpoints"
        switchover.completed_at = datetime.now(timezone.utc)
        await db.flush()
    except Exception as exc:
        previous_provider_catalog_entry_id = execution_state.get("rollback_checkpoint", {}).get(
            "previous_provider_catalog_entry_id",
            binding.provider_catalog_entry_id,
        )
        binding.provider_catalog_entry_id = previous_provider_catalog_entry_id
        binding.status = BindingStatus.ACTIVE
        binding.readiness_detail = "switchover rollback to previous provider"
        binding.last_transition_actor_user_id = actor.id
        binding.last_transition_reason = "switchover_rollback"
        binding.last_transition_at = datetime.now(timezone.utc)
        touch_updated_at(binding)
        execution_state["rollback_checkpoint"] = {
            "required": False,
            "previous_provider_catalog_entry_id": previous_provider_catalog_entry_id,
        }
        execution_state["phase"] = "rollback_complete"
        execution_state["last_error"] = str(exc)
        switchover.execution_state_json = execution_state
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
        payload={
            "binding_id": binding.id,
            "strategy": switchover.strategy,
            "retirement_strategy": switchover.retirement_strategy,
            "execution_phase": (switchover.execution_state_json or {}).get("phase", "completed"),
        },
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

    missing_secret_kinds, missing_secret_detail = await _required_secret_validation_detail(
        db,
        binding_id=binding.id,
        provider=provider,
    )

    supported_regions = provider.metadata_json.get("supported_regions", ["global"])
    region_valid = region is None or "global" in supported_regions or region in supported_regions
    if missing_secret_kinds or not region_valid:
        binding.status = BindingStatus.FAILED
        details = []
        if missing_secret_kinds:
            details.append(f"missing or expired secrets: {missing_secret_detail}")
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


async def _list_bindings_using_secret_family(
    db: AsyncSession,
    *,
    environment_id: int,
    name: str,
    provider_key: str,
    secret_kind: str,
) -> list[int]:
    return (
        await db.execute(
            select(BindingSecretRef.binding_id)
            .join(SecretRef, BindingSecretRef.secret_ref_id == SecretRef.id)
            .where(
                SecretRef.environment_id == environment_id,
                SecretRef.name == name,
                SecretRef.provider_key == provider_key,
                SecretRef.secret_kind == secret_kind,
            )
            .distinct()
        )
    ).scalars().all()


async def _resolve_latest_valid_secret_for_anchor(db: AsyncSession, *, anchor_secret: SecretRef) -> SecretRef | None:
    now = datetime.now(timezone.utc)
    return (
        await db.execute(
            select(SecretRef)
            .where(
                SecretRef.environment_id == anchor_secret.environment_id,
                SecretRef.name == anchor_secret.name,
                SecretRef.provider_key == anchor_secret.provider_key,
                SecretRef.secret_kind == anchor_secret.secret_kind,
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


async def _required_secret_validation_detail(
    db: AsyncSession,
    *,
    binding_id: int,
    provider: ProviderCatalogEntry,
) -> tuple[list[str], str]:
    required_secret_kinds = provider.metadata_json.get("required_secret_kinds", [])
    anchor_secrets = (
        await db.execute(
            select(SecretRef)
            .join(BindingSecretRef, BindingSecretRef.secret_ref_id == SecretRef.id)
            .where(BindingSecretRef.binding_id == binding_id)
        )
    ).scalars().all()
    resolved_by_kind: dict[str, SecretRef] = {}
    for anchor in anchor_secrets:
        latest_valid = await _resolve_latest_valid_secret_for_anchor(db, anchor_secret=anchor)
        if latest_valid is not None and latest_valid.secret_kind not in resolved_by_kind:
            resolved_by_kind[latest_valid.secret_kind] = latest_valid
    missing_secret_kinds = sorted(set(required_secret_kinds) - set(resolved_by_kind.keys()))
    return missing_secret_kinds, ", ".join(missing_secret_kinds)


async def _validate_binding_activation_prerequisites(
    db: AsyncSession,
    *,
    binding: CapabilityBinding,
    provider: ProviderCatalogEntry,
) -> None:
    missing_secret_kinds, missing_secret_detail = await _required_secret_validation_detail(
        db,
        binding_id=binding.id,
        provider=provider,
    )
    if missing_secret_kinds:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot activate binding: missing or expired secrets [{missing_secret_detail}]",
        )


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
        provider = await db.get(ProviderCatalogEntry, binding.provider_catalog_entry_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
        await _validate_binding_activation_prerequisites(db, binding=binding, provider=provider)

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
            if item.environment_id == environment.id and item.status in {MigrationStatus.QUEUED, MigrationStatus.PENDING}
        )
        drifted_migrations = sum(
            1
            for item in migrations
            if item.environment_id == environment.id and item.reconciliation_status == "drifted"
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
                "drifted_migrations": drifted_migrations,
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


def _is_region_compatible(
    *,
    supported_regions: list[str],
    requested_region: str | None,
    environment_region_preference: str | None,
) -> tuple[bool, str]:
    region_to_validate = requested_region or environment_region_preference
    supported = set(supported_regions)
    if not region_to_validate:
        return True, "no region preference defined"
    if "global" in supported or region_to_validate in supported:
        return True, f"region '{region_to_validate}' is supported"
    return False, f"region '{region_to_validate}' is not in target supported regions: {sorted(supported)}"


async def _build_switchover_preflight_report(
    db: AsyncSession,
    *,
    binding: CapabilityBinding,
    target_provider: ProviderCatalogEntry,
    environment: Environment,
) -> dict[str, Any]:
    current_provider = await db.get(ProviderCatalogEntry, binding.provider_catalog_entry_id)
    if current_provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Current provider not found")
    capability_type = await db.get(CapabilityType, binding.capability_type_id)
    if capability_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found")
    capability_key = CapabilityKey(capability_type.key)
    current_profile, target_profile = _load_provider_profiles(
        capability_key=capability_key,
        current_provider_key=current_provider.provider_key,
        target_provider_key=target_provider.provider_key,
    )
    current_health = await provider_registry.resolve(capability_key, current_profile.provider_key).health()
    target_health = await provider_registry.resolve(capability_key, target_profile.provider_key).health()
    missing_secret_kinds, _ = await _required_secret_validation_detail(
        db,
        binding_id=binding.id,
        provider=target_provider,
    )
    region_ok, region_detail = _is_region_compatible(
        supported_regions=target_profile.supported_regions,
        requested_region=binding.region,
        environment_region_preference=environment.region_preference,
    )
    blocking_statuses = {MigrationStatus.PENDING, MigrationStatus.QUEUED, MigrationStatus.FAILED}
    unresolved_migrations = (
        await db.execute(
            select(SchemaMigration).where(
                SchemaMigration.environment_id == environment.id,
                SchemaMigration.status.in_(blocking_statuses),
            )
        )
    ).scalars().all()
    migration_ready = len(unresolved_migrations) == 0
    return {
        "health": {
            "ok": current_health.ready and target_health.ready,
            "current_provider_ready": current_health.ready,
            "target_provider_ready": target_health.ready,
            "detail": f"current={current_health.detail}; target={target_health.detail}",
        },
        "secrets": {
            "ok": len(missing_secret_kinds) == 0,
            "missing_secret_kinds": missing_secret_kinds,
        },
        "region_compatibility": {
            "ok": region_ok,
            "detail": region_detail,
            "target_supported_regions": target_profile.supported_regions,
        },
        "migration_readiness": {
            "ok": migration_ready,
            "blocking_migrations": [item.version for item in unresolved_migrations],
        },
    }


def _preflight_is_ready(preflight_report: dict[str, Any]) -> bool:
    return all(item.get("ok") for item in preflight_report.values() if isinstance(item, dict))
