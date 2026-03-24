from __future__ import annotations

from datetime import timezone, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import decode_id_or_404, encode_id
from src.apps.multitenancy.models.tenant import TenantMember, TenantRole
from src.postbase.domain.enums import (
    ApiKeyRole,
    BindingStatus,
    CapabilityKey,
    MigrationStatus,
    PolicyMode,
    SecretStatus,
    SwitchoverStatus,
)
from src.postbase.domain.models import (
    AuditLog,
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


ROLE_ORDER = {TenantRole.MEMBER: 0, TenantRole.ADMIN: 1, TenantRole.OWNER: 2}
REQUIRED_OPERATIONS: dict[CapabilityKey, set[str]] = {
    CapabilityKey.AUTH: {"signup", "login", "refresh", "me", "logout"},
    CapabilityKey.DATA: {"namespaces", "tables", "crud"},
    CapabilityKey.STORAGE: {"upload", "list", "signed_url", "delete"},
    CapabilityKey.FUNCTIONS: {"create", "list", "invoke", "executions"},
    CapabilityKey.EVENTS: {"channels", "subscriptions", "publish"},
}


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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient tenant access")
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
    secret_ref.value_hash = hash_secret(secret_value)
    secret_ref.last_four = secret_value[-4:] if secret_value else ""
    secret_ref.status = SecretStatus.ACTIVE
    touch_updated_at(secret_ref)
    await db.flush()
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
    db.add(
        SchemaMigration(
            environment_id=environment.id,
            namespace_id=namespace.id,
            table_definition_id=provider_entry.id,
            version=f"{provider_entry.id:04d}",
            status=MigrationStatus.APPLIED,
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
        status=SwitchoverStatus.COMPLETED,
        requested_by_user_id=actor.id,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(switchover)
    binding.provider_catalog_entry_id = target_provider.id
    binding.status = BindingStatus.ACTIVE
    touch_updated_at(binding)
    await db.flush()
    await record_audit_event(
        db,
        action="binding.switchover_completed",
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


async def set_binding_status(
    db: AsyncSession,
    *,
    binding: CapabilityBinding,
    status_value: BindingStatus,
    actor: User,
    project: Project,
    environment: Environment,
) -> CapabilityBinding:
    binding.status = status_value
    touch_updated_at(binding)
    await db.flush()
    await record_audit_event(
        db,
        action="binding.status_updated",
        entity_type="capability_binding",
        entity_id=str(binding.id),
        actor_user_id=actor.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"status": status_value.value},
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
        environment_health = health_by_environment[environment.id]
        environment_rows.append(
            {
                "environment_id": encode_id(environment.id),
                "stage": environment.stage,
                "active_bindings": environment_health["active"],
                "degraded_bindings": environment_health["degraded"],
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
