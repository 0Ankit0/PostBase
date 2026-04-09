from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.schemas import PaginatedResponse
from src.apps.iam.api.deps import get_current_user, get_db
from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import decode_id_or_404, encode_id
from src.apps.multitenancy.models.tenant import TenantRole
from src.postbase.control_plane.schemas import (
    AuditLogRead,
    BindingCreate,
    BindingRead,
    BindingStatusUpdate,
    CapabilityHealthReport,
    EnvironmentApiKeyCreate,
    EnvironmentApiKeyIssued,
    EnvironmentApiKeyRead,
    EnvironmentCreate,
    EnvironmentRead,
    NamespaceCreate,
    NamespaceRead,
    MigrationRead,
    MigrationRollbackResult,
    ProjectOverviewRead,
    ProjectCreate,
    ProjectRead,
    ProviderCatalogRead,
    ProviderHealthRead,
    SecretRotate,
    SecretRotateResult,
    SecretRefCreate,
    SecretRefRead,
    SwitchoverCreate,
    SwitchoverRead,
    TableCreate,
    TableRead,
    UsageMeterRead,
    WebhookDrainResult,
    WebhookRecoveryResult,
)
from src.postbase.control_plane.service import (
    build_capability_health_report,
    build_project_overview,
    create_switchover_plan,
    create_binding_version,
    execute_switchover_plan,
    create_table_metadata,
    create_environment_for_project,
    create_namespace_metadata,
    create_project_for_tenant,
    create_secret_ref,
    apply_schema_migration,
    retry_schema_migration,
    cancel_schema_migration,
    ensure_environment_access,
    get_project_usage_meters,
    require_project_access,
    revoke_secret_ref,
    rotate_secret_ref,
    set_binding_status,
)
from src.postbase.domain.enums import MigrationStatus
from src.postbase.domain.models import (
    AuditLog,
    BindingSecretRef,
    CapabilityBinding,
    CapabilityType,
    Environment,
    EnvironmentApiKey,
    Project,
    ProviderCatalogEntry,
    SecretRef,
    SchemaMigration,
    SwitchoverPlan,
    DataNamespace,
    TableDefinition,
    UsageMeter,
    WebhookDeliveryJob,
)
from src.postbase.platform.access import issue_environment_api_key
from src.postbase.platform.audit import record_audit_event
from src.postbase.platform.seeding import seed_provider_catalog
from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider
from src.postbase.tasks import drain_due_webhook_jobs

router = APIRouter(tags=["postbase-control-plane"])
MUTATION_MIN_ROLE = TenantRole.ADMIN
CONTROL_PLANE_MUTATION_MIN_ROLES: dict[str, TenantRole] = {
    "bindings": TenantRole.ADMIN,
    "switchovers": TenantRole.ADMIN,
    "secrets": TenantRole.ADMIN,
    "migrations": TenantRole.ADMIN,
    "webhook_drain": TenantRole.ADMIN,
    "webhook_recover": TenantRole.ADMIN,
    "environment_keys": TenantRole.ADMIN,
    "namespaces": TenantRole.ADMIN,
    "tables": TenantRole.ADMIN,
}


async def _load_environment_or_404(db: AsyncSession, environment_id: str) -> Environment:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    return environment


async def _authorize_environment_mutation(
    db: AsyncSession,
    *,
    environment: Environment,
    current_user: User,
    action: str,
) -> Project:
    min_role = CONTROL_PLANE_MUTATION_MIN_ROLES.get(action, MUTATION_MIN_ROLE)
    return await ensure_environment_access(
        db,
        environment=environment,
        user_id=current_user.id,
        min_role=min_role,
    )


async def _load_binding_environment_and_project(
    db: AsyncSession,
    *,
    binding_id: str,
    current_user: User,
    action: str,
) -> tuple[CapabilityBinding, Environment, Project]:
    binding_db_id = decode_id_or_404(binding_id)
    binding = await db.get(CapabilityBinding, binding_db_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    environment = await db.get(Environment, binding.environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action=action,
    )
    return binding, environment, project


async def _load_switchover_context(
    db: AsyncSession,
    *,
    switchover_id: str,
    current_user: User,
    action: str,
) -> tuple[SwitchoverPlan, CapabilityBinding, Environment, Project]:
    switchover_db_id = decode_id_or_404(switchover_id)
    switchover = await db.get(SwitchoverPlan, switchover_db_id)
    if switchover is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Switchover not found")
    binding = await db.get(CapabilityBinding, switchover.capability_binding_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    environment = await db.get(Environment, binding.environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action=action,
    )
    return switchover, binding, environment, project


async def _to_binding_read(
    db: AsyncSession,
    binding: CapabilityBinding,
    capability: CapabilityType,
    provider: ProviderCatalogEntry,
) -> BindingRead:
    linked_secret_ids = (
        await db.execute(
            select(BindingSecretRef.secret_ref_id).where(BindingSecretRef.binding_id == binding.id)
        )
    ).scalars().all()
    return BindingRead(
        id=binding.id,
        environment_id=binding.environment_id,
        capability_key=capability.key,
        provider_key=provider.provider_key,
        adapter_version=provider.adapter_version,
        status=binding.status,
        readiness_detail=binding.readiness_detail,
        linked_secret_ref_ids=[encode_id(i) for i in linked_secret_ids],
        supersedes_binding_id=encode_id(binding.supersedes_binding_id) if binding.supersedes_binding_id else None,
        last_transition_actor_user_id=encode_id(binding.last_transition_actor_user_id)
        if binding.last_transition_actor_user_id
        else None,
        last_transition_reason=binding.last_transition_reason,
        last_transition_at=binding.last_transition_at,
        region=binding.region,
        config_json=binding.config_json,
    )


@router.get("/provider-catalog", response_model=list[ProviderCatalogRead])
async def list_provider_catalog(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProviderCatalogRead]:
    await seed_provider_catalog(db)
    rows = (
        await db.execute(select(ProviderCatalogEntry, CapabilityType).join(CapabilityType))
    ).all()
    _ = current_user  # authenticated access only
    return [
        ProviderCatalogRead(
            id=entry.id,
            capability_key=capability.key,
            provider_key=entry.provider_key,
            adapter_version=entry.adapter_version,
            certification_state=entry.certification_state.value,
            metadata_json=entry.metadata_json,
        )
        for entry, capability in rows
    ]


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    return await create_project_for_tenant(
        db,
        tenant_id_hash=payload.tenant_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        actor=current_user,
    )


@router.get("/projects", response_model=PaginatedResponse[ProjectRead])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[ProjectRead]:
    rows = (await db.execute(select(Project))).scalars().all()
    visible: list[Project] = []
    for project in rows:
        try:
            await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.MEMBER)
        except HTTPException:
            continue
        visible.append(project)
    return PaginatedResponse[ProjectRead].create(
        items=[ProjectRead.model_validate(item) for item in visible],
        total=len(visible),
        skip=0,
        limit=len(visible) or 1,
    )


@router.post(
    "/projects/{project_id}/environments",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment(
    project_id: str,
    payload: EnvironmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Environment:
    return await create_environment_for_project(
        db,
        project_id_hash=project_id,
        name=payload.name,
        slug=payload.slug,
        stage=payload.stage.value,
        region_preference=payload.region_preference,
        actor=current_user,
    )


@router.get("/projects/{project_id}/environments", response_model=list[EnvironmentRead])
async def list_environments(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Environment]:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.MEMBER)
    rows = (
        await db.execute(select(Environment).where(Environment.project_id == project.id))
    ).scalars().all()
    return rows


@router.get("/environments/{environment_id}/bindings", response_model=list[BindingRead])
async def list_bindings(
    environment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BindingRead]:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(db, environment=environment, user_id=current_user.id, min_role=TenantRole.MEMBER)
    rows = (
        await db.execute(
            select(CapabilityBinding, CapabilityType, ProviderCatalogEntry)
            .join(CapabilityType, CapabilityBinding.capability_type_id == CapabilityType.id)
            .join(
                ProviderCatalogEntry,
                CapabilityBinding.provider_catalog_entry_id == ProviderCatalogEntry.id,
            )
            .where(CapabilityBinding.environment_id == environment.id)
        )
    ).all()
    response: list[BindingRead] = []
    for binding, capability, provider in rows:
        response.append(await _to_binding_read(db, binding, capability, provider))
    return response


@router.post("/environments/{environment_id}/bindings", response_model=BindingRead)
async def upsert_binding(
    environment_id: str,
    payload: BindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BindingRead:
    environment = await _load_environment_or_404(db, environment_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="bindings",
    )
    capability = (
        await db.execute(select(CapabilityType).where(CapabilityType.key == payload.capability_key))
    ).scalars().first()
    if capability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found")
    provider = (
        await db.execute(
            select(ProviderCatalogEntry).where(
                ProviderCatalogEntry.capability_type_id == capability.id,
                ProviderCatalogEntry.provider_key == payload.provider_key,
            )
        )
    ).scalars().first()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    secret_ref_ids = [decode_id_or_404(secret_ref_id) for secret_ref_id in payload.secret_ref_ids]
    binding = await create_binding_version(
        db,
        environment=environment,
        capability=capability,
        provider=provider,
        actor=current_user,
        project=project,
        config_json=payload.config_json,
        region=payload.region,
        secret_ref_ids=secret_ref_ids,
    )
    return await _to_binding_read(db, binding, capability, provider)


@router.post("/bindings/{binding_id}/switchovers", response_model=SwitchoverRead)
async def create_switchover(
    binding_id: str,
    payload: SwitchoverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SwitchoverPlan:
    binding, environment, project = await _load_binding_environment_and_project(
        db,
        binding_id=binding_id,
        current_user=current_user,
        action="switchovers",
    )
    return await create_switchover_plan(
        db,
        binding=binding,
        target_provider_key=payload.target_provider_key,
        actor=current_user,
        project=project,
        environment=environment,
        strategy=payload.strategy,
    )


@router.post("/switchovers/{switchover_id}/execute", response_model=SwitchoverRead)
async def execute_switchover(
    switchover_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SwitchoverPlan:
    switchover, _, environment, project = await _load_switchover_context(
        db,
        switchover_id=switchover_id,
        current_user=current_user,
        action="switchovers",
    )
    return await execute_switchover_plan(
        db,
        switchover=switchover,
        actor=current_user,
        project=project,
        environment=environment,
    )


@router.get("/bindings/{binding_id}/switchovers", response_model=list[SwitchoverRead])
async def list_binding_switchovers(
    binding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SwitchoverPlan]:
    binding_db_id = decode_id_or_404(binding_id)
    binding = await db.get(CapabilityBinding, binding_db_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    environment = await db.get(Environment, binding.environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(
        db,
        environment=environment,
        user_id=current_user.id,
        min_role=TenantRole.ADMIN,
    )
    return (
        await db.execute(
            select(SwitchoverPlan)
            .where(SwitchoverPlan.capability_binding_id == binding.id)
            .order_by(SwitchoverPlan.created_at.desc())
        )
    ).scalars().all()


@router.get("/switchovers/{switchover_id}", response_model=SwitchoverRead)
async def get_switchover(
    switchover_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SwitchoverPlan:
    switchover_db_id = decode_id_or_404(switchover_id)
    switchover = await db.get(SwitchoverPlan, switchover_db_id)
    if switchover is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Switchover not found")
    binding = await db.get(CapabilityBinding, switchover.capability_binding_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    environment = await db.get(Environment, binding.environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(
        db,
        environment=environment,
        user_id=current_user.id,
        min_role=TenantRole.MEMBER,
    )
    return switchover


@router.post("/bindings/{binding_id}/status", response_model=BindingRead)
async def update_binding_status(
    binding_id: str,
    payload: BindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BindingRead:
    binding, environment, project = await _load_binding_environment_and_project(
        db,
        binding_id=binding_id,
        current_user=current_user,
        action="bindings",
    )
    capability = await db.get(CapabilityType, binding.capability_type_id)
    provider = await db.get(ProviderCatalogEntry, binding.provider_catalog_entry_id)
    if capability is None or provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding metadata not found")
    binding = await set_binding_status(
        db,
        binding=binding,
        status_value=payload.status,
        reason=payload.reason,
        actor=current_user,
        project=project,
        environment=environment,
    )
    return await _to_binding_read(db, binding, capability, provider)


@router.get("/environments/{environment_id}/keys", response_model=list[EnvironmentApiKeyRead])
async def list_environment_keys(
    environment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EnvironmentApiKey]:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(db, environment=environment, user_id=current_user.id, min_role=TenantRole.ADMIN)
    return (
        await db.execute(
            select(EnvironmentApiKey).where(EnvironmentApiKey.environment_id == environment.id)
        )
    ).scalars().all()


@router.post("/environments/{environment_id}/keys", response_model=EnvironmentApiKeyIssued)
async def create_environment_key(
    environment_id: str,
    payload: EnvironmentApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnvironmentApiKeyIssued:
    environment = await _load_environment_or_404(db, environment_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="environment_keys",
    )
    api_key, plaintext_key = await issue_environment_api_key(
        db,
        environment_id=environment.id,
        name=payload.name,
        role=payload.role,
    )
    await record_audit_event(
        db,
        action="key.issued",
        entity_type="environment_api_key",
        entity_id=str(api_key.id),
        actor_user_id=current_user.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"name": payload.name, "role": payload.role.value},
    )
    await db.commit()
    await db.refresh(api_key)
    return EnvironmentApiKeyIssued(
        api_key=EnvironmentApiKeyRead.model_validate(api_key),
        plaintext_key=plaintext_key,
    )


@router.delete("/environments/{environment_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_environment_key(
    environment_id: str,
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    environment = await _load_environment_or_404(db, environment_id)
    key_db_id = decode_id_or_404(key_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="environment_keys",
    )
    key_row = await db.get(EnvironmentApiKey, key_db_id)
    if key_row is None or key_row.environment_id != environment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key_row.is_active = False
    await record_audit_event(
        db,
        action="key.revoked",
        entity_type="environment_api_key",
        entity_id=str(key_row.id),
        actor_user_id=current_user.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"name": key_row.name},
    )
    await db.commit()


@router.get("/environments/{environment_id}/secrets", response_model=list[SecretRefRead])
async def list_environment_secrets(
    environment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SecretRef]:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(db, environment=environment, user_id=current_user.id, min_role=TenantRole.ADMIN)
    return (
        await db.execute(select(SecretRef).where(SecretRef.environment_id == environment.id))
    ).scalars().all()


@router.post("/environments/{environment_id}/secrets", response_model=SecretRefRead, status_code=status.HTTP_201_CREATED)
async def create_environment_secret(
    environment_id: str,
    payload: SecretRefCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SecretRef:
    environment = await _load_environment_or_404(db, environment_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="secrets",
    )
    return await create_secret_ref(
        db,
        environment=environment,
        project=project,
        actor=current_user,
        name=payload.name,
        provider_key=payload.provider_key,
        secret_kind=payload.secret_kind,
        secret_value=payload.secret_value,
    )


@router.post("/environments/{environment_id}/secrets/{secret_id}/rotate", response_model=SecretRotateResult)
async def rotate_environment_secret(
    environment_id: str,
    secret_id: str,
    payload: SecretRotate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SecretRotateResult:
    environment = await _load_environment_or_404(db, environment_id)
    secret_db_id = decode_id_or_404(secret_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="secrets",
    )
    secret_ref = await db.get(SecretRef, secret_db_id)
    if secret_ref is None or secret_ref.environment_id != environment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    updated_secret = await rotate_secret_ref(
        db,
        secret_ref=secret_ref,
        project=project,
        environment=environment,
        actor=current_user,
        secret_value=payload.secret_value,
    )
    impacted_binding_ids = (
        await db.execute(
            select(BindingSecretRef.binding_id).where(BindingSecretRef.secret_ref_id == secret_ref.id)
        )
    ).scalars().all()
    _, provider_health, _ = await build_capability_health_report(db, environment=environment, project=project)
    return SecretRotateResult(
        secret=SecretRefRead.model_validate(updated_secret),
        impacted_binding_ids=[encode_id(item) for item in impacted_binding_ids],
        post_rotation_health_check=[ProviderHealthRead(**item) for item in provider_health],
        rollback_ready=True,
    )


@router.delete("/environments/{environment_id}/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_environment_secret(
    environment_id: str,
    secret_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    environment = await _load_environment_or_404(db, environment_id)
    secret_db_id = decode_id_or_404(secret_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="secrets",
    )
    secret_ref = await db.get(SecretRef, secret_db_id)
    if secret_ref is None or secret_ref.environment_id != environment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    await revoke_secret_ref(
        db,
        secret_ref=secret_ref,
        project=project,
        environment=environment,
        actor=current_user,
    )


@router.get("/projects/{project_id}/audit", response_model=list[AuditLogRead])
async def list_project_audit_logs(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AuditLog]:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.ADMIN)
    return (
        await db.execute(
            select(AuditLog).where(AuditLog.project_id == project.id).order_by(AuditLog.created_at.desc())
        )
    ).scalars().all()


@router.get("/environments/{environment_id}/reports/capability-health", response_model=CapabilityHealthReport)
async def get_capability_health_report(
    environment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CapabilityHealthReport:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    project = await ensure_environment_access(
        db,
        environment=environment,
        user_id=current_user.id,
        min_role=TenantRole.ADMIN,
    )
    binding_rows, provider_health, degraded_capabilities = await build_capability_health_report(
        db,
        environment=environment,
        project=project,
    )
    bindings: list[BindingRead] = []
    for binding, capability, provider in binding_rows:
        bindings.append(await _to_binding_read(db, binding, capability, provider))
    return CapabilityHealthReport(
        environment_id=environment_id,
        bindings=bindings,
        provider_health=[ProviderHealthRead(**item) for item in provider_health],
        overall_ready=not degraded_capabilities,
        degraded_capabilities=degraded_capabilities,
    )


@router.get("/projects/{project_id}/usage", response_model=list[UsageMeterRead])
async def get_project_usage(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UsageMeter]:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.ADMIN)
    return await get_project_usage_meters(db, project=project)


@router.get("/projects/{project_id}/overview", response_model=ProjectOverviewRead)
async def get_project_overview(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOverviewRead:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.ADMIN)
    overview = await build_project_overview(db, project=project)
    return ProjectOverviewRead(**overview)




@router.post("/environments/{environment_id}/operations/webhooks/drain", response_model=WebhookDrainResult)
async def drain_environment_webhooks(
    environment_id: str,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookDrainResult:
    environment = await _load_environment_or_404(db, environment_id)
    await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="webhook_drain",
    )
    drained_count = await drain_due_webhook_jobs(limit=limit)
    return WebhookDrainResult(
        triggered=True,
        drained_count=drained_count,
        checklist=[
            {"item": "Durable webhook queue worker task registered", "completed": True},
            {"item": "Scheduled drain job configured", "completed": True},
            {"item": "Operator-triggered drain endpoint available", "completed": True},
        ],
    )


@router.post("/environments/{environment_id}/operations/webhooks/recover-exhausted", response_model=WebhookRecoveryResult)
async def recover_exhausted_webhooks(
    environment_id: str,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookRecoveryResult:
    environment = await _load_environment_or_404(db, environment_id)
    await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="webhook_recover",
    )
    failed_jobs = (
        await db.execute(
            select(WebhookDeliveryJob)
            .where(
                WebhookDeliveryJob.status == "failed",
                WebhookDeliveryJob.attempt_count >= WebhookDeliveryJob.max_attempts,
            )
            .order_by(WebhookDeliveryJob.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    for job in failed_jobs:
        job.status = "retrying"
        job.error_text = "operator initiated retry after exhaustion"
        job.next_attempt_at = datetime.now(timezone.utc)
    await db.commit()
    return WebhookRecoveryResult(
        scanned_failed_jobs=len(failed_jobs),
        requeued_jobs=len(failed_jobs),
        exhausted_job_ids=[encode_id(job.id) for job in failed_jobs if job.id is not None],
    )

@router.post("/environments/{environment_id}/data/namespaces", response_model=NamespaceRead, status_code=status.HTTP_201_CREATED)
async def create_namespace(
    environment_id: str,
    payload: NamespaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NamespaceRead:
    environment = await _load_environment_or_404(db, environment_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="namespaces",
    )
    return await create_namespace_metadata(
        db,
        environment=environment,
        project=project,
        actor=current_user,
        name=payload.name,
    )


@router.post(
    "/environments/{environment_id}/data/namespaces/{namespace_id}/tables",
    response_model=TableRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_table(
    environment_id: str,
    namespace_id: str,
    payload: TableCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TableRead:
    namespace_db_id = decode_id_or_404(namespace_id)
    environment = await _load_environment_or_404(db, environment_id)
    namespace = await db.get(DataNamespace, namespace_db_id)
    if namespace is None or namespace.environment_id != environment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Namespace not found")
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="tables",
    )
    definition = await create_table_metadata(
        db,
        namespace=namespace,
        project=project,
        environment=environment,
        actor=current_user,
        table_name=payload.table_name,
        columns=[column.model_dump() for column in payload.columns],
        policy_mode=payload.policy_mode,
        owner_column=payload.owner_column,
    )
    migration = (
        await db.execute(
            select(SchemaMigration)
            .where(SchemaMigration.table_definition_id == definition.id)
            .order_by(SchemaMigration.id.desc())
        )
    ).scalars().first()
    if migration is not None and migration.status.value == "applied":
        provider = PostgresNativeDataProvider()
        await provider.create_namespace(db, namespace)
        await provider.create_table(db, namespace, definition)
    await db.commit()
    return definition




async def _to_migration_read(db: AsyncSession, migration: SchemaMigration) -> MigrationRead:
    reconciliation_status = "pending_apply"
    if migration.status == MigrationStatus.APPLIED:
        reconciliation_status = "in_sync"
    elif migration.status == MigrationStatus.FAILED:
        reconciliation_status = "drifted"
    elif migration.status == MigrationStatus.CANCELED:
        reconciliation_status = "canceled"
    if migration.table_definition_id is not None:
        definition = await db.get(TableDefinition, migration.table_definition_id)
        if definition is None:
            reconciliation_status = "drifted"
    return MigrationRead(
        id=migration.id or 0,
        environment_id=migration.environment_id,
        namespace_id=migration.namespace_id,
        table_definition_id=migration.table_definition_id,
        version=migration.version,
        status=migration.status,
        reconciliation_status=reconciliation_status,
        applied_sql=migration.applied_sql,
        created_at=migration.created_at,
    )

@router.get("/environments/{environment_id}/migrations", response_model=list[MigrationRead])
async def list_environment_migrations(
    environment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MigrationRead]:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(
        db,
        environment=environment,
        user_id=current_user.id,
        min_role=TenantRole.ADMIN,
    )
    rows = (
        await db.execute(
            select(SchemaMigration)
            .where(SchemaMigration.environment_id == environment.id)
            .order_by(SchemaMigration.id.desc())
        )
    ).scalars().all()
    return [await _to_migration_read(db, row) for row in rows]


@router.post(
    "/environments/{environment_id}/migrations/{migration_id}/apply",
    response_model=MigrationRead,
)
async def apply_environment_migration(
    environment_id: str,
    migration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MigrationRead:
    environment = await _load_environment_or_404(db, environment_id)
    migration_db_id = decode_id_or_404(migration_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="migrations",
    )
    migration = await db.get(SchemaMigration, migration_db_id)
    if migration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")
    migration = await apply_schema_migration(
        db,
        migration=migration,
        environment=environment,
        project=project,
        actor=current_user,
    )
    return await _to_migration_read(db, migration)


@router.post(
    "/environments/{environment_id}/migrations/{migration_id}/retry",
    response_model=MigrationRollbackResult,
)
async def retry_environment_migration(
    environment_id: str,
    migration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MigrationRollbackResult:
    environment = await _load_environment_or_404(db, environment_id)
    migration_db_id = decode_id_or_404(migration_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="migrations",
    )
    migration = await db.get(SchemaMigration, migration_db_id)
    if migration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")
    migration = await retry_schema_migration(
        db,
        migration=migration,
        environment=environment,
        project=project,
        actor=current_user,
    )
    migration_read = await _to_migration_read(db, migration)
    return MigrationRollbackResult(
        migration=migration_read,
        rollback_sql=f"-- retry for migration {migration.version}",
        rollback_status="requested",
    )


@router.post(
    "/environments/{environment_id}/migrations/{migration_id}/cancel",
    response_model=MigrationRollbackResult,
)
async def cancel_environment_migration(
    environment_id: str,
    migration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MigrationRollbackResult:
    environment = await _load_environment_or_404(db, environment_id)
    migration_db_id = decode_id_or_404(migration_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="migrations",
    )
    migration = await db.get(SchemaMigration, migration_db_id)
    if migration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")
    migration = await cancel_schema_migration(
        db,
        migration=migration,
        environment=environment,
        project=project,
        actor=current_user,
    )
    migration_read = await _to_migration_read(db, migration)
    return MigrationRollbackResult(
        migration=migration_read,
        rollback_sql="-- canceled migration",
        rollback_status="canceled",
    )
