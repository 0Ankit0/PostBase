from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.schemas import PaginatedResponse
from src.apps.iam.api.deps import get_current_user, get_db
from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import decode_id_or_404, encode_id
from src.apps.multitenancy.models.tenant import TenantMember, TenantRole
from src.postbase.control_plane.schemas import (
    AuditLogRead,
    BindingCreate,
    BindingRead,
    BindingStatusUpdate,
    CapabilityHealthReport,
    CertificationRunCreate,
    CertificationRunRead,
    ComplianceEvidenceBundleRead,
    EnvironmentApiKeyCreate,
    EnvironmentApiKeyIssued,
    EnvironmentApiKeyRead,
    EnvironmentCreate,
    EnvironmentLifecycleUpdate,
    EnvironmentRead,
    NamespaceCreate,
    NamespaceRead,
    MigrationRead,
    MigrationRollbackResult,
    ProjectOverviewRead,
    ProjectCreate,
    ProjectLifecycleUpdate,
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
    AuditExportRead,
    WebhookDrainResult,
    WebhookRecoveryResult,
)
from src.postbase.control_plane.service import (
    build_capability_health_report,
    build_project_overview,
    create_switchover_plan,
    create_certification_run,
    create_binding_version,
    execute_switchover_plan,
    rollback_switchover_plan,
    approve_certification_run,
    publish_certification_run,
    create_table_metadata,
    create_environment_for_project,
    create_namespace_metadata,
    create_project_for_tenant,
    set_project_lifecycle_state,
    set_environment_lifecycle_state,
    create_secret_ref,
    build_idempotency_endpoint_fingerprint,
    build_idempotency_request_hash,
    check_idempotency_replay,
    apply_schema_migration,
    retry_schema_migration,
    reserve_idempotency_key,
    cancel_schema_migration,
    execute_migration_reconciliation,
    ensure_environment_access,
    enforce_quota_lifecycle,
    refresh_migration_reconciliation_state,
    require_project_access,
    revoke_secret_ref,
    rotate_secret_ref,
    set_binding_status,
    persist_idempotency_success,
)
from src.postbase.capabilities.events.webhook_jobs import replay_dead_letter_webhook_jobs
from src.postbase.domain.models import (
    AuditLog,
    BindingSecretRef,
    CertificationRun,
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
    UsageMeter,
)
from src.postbase.platform.access import issue_environment_api_key
from src.postbase.platform.audit import build_compliance_evidence_bundle, query_audit_logs, record_audit_event, serialize_audit_export
from src.apps.core.config import settings
from src.postbase.platform.seeding import seed_provider_catalog
from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider
from src.postbase.tasks import drain_due_webhook_jobs

router = APIRouter(tags=["postbase-control-plane"])
DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100
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
    "environment_lifecycle": TenantRole.ADMIN,
}
TMutationResult = TypeVar("TMutationResult")


def _allowed_roles(min_role: TenantRole) -> tuple[TenantRole, ...]:
    if min_role == TenantRole.OWNER:
        return (TenantRole.OWNER,)
    if min_role == TenantRole.ADMIN:
        return (TenantRole.OWNER, TenantRole.ADMIN)
    return (TenantRole.OWNER, TenantRole.ADMIN, TenantRole.MEMBER)


async def _execute_idempotent_mutation(
    *,
    request: Request,
    db: AsyncSession,
    current_user: User,
    request_payload: dict[str, Any],
    success_status_code: int,
    execute: Callable[[], Awaitable[TMutationResult]],
    serialize_response: Callable[[TMutationResult], dict[str, Any]],
) -> TMutationResult | JSONResponse:
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return await execute()

    endpoint_path = request.scope.get("route").path if request.scope.get("route") else request.url.path
    endpoint_fingerprint = build_idempotency_endpoint_fingerprint(method=request.method, path=endpoint_path)
    request_hash = build_idempotency_request_hash(
        {
            "path_params": request.path_params,
            "query_params": sorted(request.query_params.multi_items()),
            "payload": request_payload,
        }
    )
    replay = await check_idempotency_replay(
        db,
        idempotency_key=idempotency_key,
        actor_user_id=current_user.id,
        endpoint_fingerprint=endpoint_fingerprint,
        request_hash=request_hash,
    )
    if replay is not None:
        return JSONResponse(status_code=replay.status_code, content=replay.response_json)

    try:
        idempotency_record = await reserve_idempotency_key(
            db,
            idempotency_key=idempotency_key,
            actor_user_id=current_user.id,
            endpoint_fingerprint=endpoint_fingerprint,
            request_hash=request_hash,
        )
    except IntegrityError:
        await db.rollback()
        replay = await check_idempotency_replay(
            db,
            idempotency_key=idempotency_key,
            actor_user_id=current_user.id,
            endpoint_fingerprint=endpoint_fingerprint,
            request_hash=request_hash,
        )
        if replay is not None:
            return JSONResponse(status_code=replay.status_code, content=replay.response_json)
        raise

    result = await execute()
    await persist_idempotency_success(
        db,
        idempotency_record=idempotency_record,
        response_status_code=success_status_code,
        response_json=serialize_response(result),
    )
    await db.commit()
    return result


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
    project = await ensure_environment_access(
        db,
        environment=environment,
        user_id=current_user.id,
        min_role=min_role,
        policy_resource="postbase.control_plane",
        policy_action=action,
    )
    usage_total = (
        await db.execute(select(func.coalesce(func.sum(UsageMeter.value), 0.0)).where(UsageMeter.environment_id == environment.id))
    ).scalar_one()
    quota = (environment.env_policy_json or {}).get("quota", {})
    enforce_quota_lifecycle(
        usage_total=float(usage_total or 0.0),
        warning_threshold=float(quota.get("warning_threshold", 750.0)),
        soft_limit=float(quota.get("soft_limit", 1000.0)),
        hard_limit=float(quota.get("hard_limit", 1200.0)),
        action=action,
    )
    return project


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


async def _create_switchover_execute(
    *,
    db: AsyncSession,
    binding_id: str,
    payload: SwitchoverCreate,
    current_user: User,
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
        retirement_strategy=payload.retirement_strategy,
        canary_traffic_percent=payload.canary_traffic_percent,
        canary_health_checkpoint_count=payload.canary_health_checkpoint_count,
        auto_abort_error_rate=payload.auto_abort_error_rate,
        simulated_canary_error_rate=payload.simulated_canary_error_rate,
    )


async def _execute_switchover_execute(
    *,
    db: AsyncSession,
    switchover_id: str,
    current_user: User,
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


@router.get("/provider-catalog", response_model=PaginatedResponse[ProviderCatalogRead])
async def list_provider_catalog(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[ProviderCatalogRead]:
    await seed_provider_catalog(db)
    total = (await db.execute(select(func.count()).select_from(ProviderCatalogEntry))).scalar_one()
    rows = (
        await db.execute(
            select(ProviderCatalogEntry, CapabilityType)
            .join(CapabilityType)
            .order_by(ProviderCatalogEntry.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    _ = current_user  # authenticated access only
    return PaginatedResponse[ProviderCatalogRead].create(
        items=[
        ProviderCatalogRead(
            id=entry.id,
            capability_key=capability.key,
            provider_key=entry.provider_key,
            adapter_version=entry.adapter_version,
            certification_state=entry.certification_state.value,
            metadata_json=entry.metadata_json,
        )
        for entry, capability in rows
    ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: Request,
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload=payload.model_dump(mode="json"),
        success_status_code=status.HTTP_201_CREATED,
        execute=lambda: create_project_for_tenant(
            db,
            tenant_id_hash=payload.tenant_id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            actor=current_user,
        ),
        serialize_response=lambda project: ProjectRead.model_validate(project).model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.post("/projects/{project_id}/lifecycle", response_model=ProjectRead)
async def update_project_lifecycle(
    project_id: str,
    payload: ProjectLifecycleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return await set_project_lifecycle_state(
        db,
        project=project,
        actor=current_user,
        is_active=payload.is_active,
    )


@router.get("/projects", response_model=PaginatedResponse[ProjectRead])
async def list_projects(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[ProjectRead]:
    membership_predicate = (
        (TenantMember.user_id == current_user.id)
        & (TenantMember.is_active == True)
        & (TenantMember.role.in_(_allowed_roles(TenantRole.MEMBER)))
    )
    base_stmt = select(Project).join(TenantMember, (TenantMember.tenant_id == Project.tenant_id) & membership_predicate)
    total = (
        await db.execute(
            select(func.count())
            .select_from(Project)
            .join(TenantMember, (TenantMember.tenant_id == Project.tenant_id) & membership_predicate)
        )
    ).scalar_one()
    rows = (await db.execute(base_stmt.order_by(Project.id.desc()).offset(skip).limit(limit))).scalars().all()
    return PaginatedResponse[ProjectRead].create(
        items=[ProjectRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/projects/{project_id}/environments",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment(
    request: Request,
    project_id: str,
    payload: EnvironmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Environment:
    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"project_id": project_id, **payload.model_dump(mode="json")},
        success_status_code=status.HTTP_201_CREATED,
        execute=lambda: create_environment_for_project(
            db,
            project_id_hash=project_id,
            name=payload.name,
            slug=payload.slug,
            stage=payload.stage.value,
            region_preference=payload.region_preference,
            actor=current_user,
        ),
        serialize_response=lambda environment: EnvironmentRead.model_validate(environment).model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.get("/projects/{project_id}/environments", response_model=PaginatedResponse[EnvironmentRead])
async def list_environments(
    project_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[EnvironmentRead]:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.MEMBER)
    total = (
        await db.execute(select(func.count()).select_from(Environment).where(Environment.project_id == project.id))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Environment)
            .where(Environment.project_id == project.id)
            .order_by(Environment.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return PaginatedResponse[EnvironmentRead].create(
        items=[EnvironmentRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/environments/{environment_id}/lifecycle", response_model=EnvironmentRead)
async def update_environment_lifecycle(
    environment_id: str,
    payload: EnvironmentLifecycleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Environment:
    environment = await _load_environment_or_404(db, environment_id)
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="environment_lifecycle",
    )
    return await set_environment_lifecycle_state(
        db,
        environment=environment,
        project=project,
        actor=current_user,
        status_value=payload.status,
        is_active=payload.is_active,
        reason=payload.reason,
    )


@router.get("/environments/{environment_id}/bindings", response_model=PaginatedResponse[BindingRead])
async def list_bindings(
    environment_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[BindingRead]:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(db, environment=environment, user_id=current_user.id, min_role=TenantRole.MEMBER)
    total = (
        await db.execute(
            select(func.count())
            .select_from(CapabilityBinding)
            .where(CapabilityBinding.environment_id == environment.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(CapabilityBinding, CapabilityType, ProviderCatalogEntry)
            .join(CapabilityType, CapabilityBinding.capability_type_id == CapabilityType.id)
            .join(
                ProviderCatalogEntry,
                CapabilityBinding.provider_catalog_entry_id == ProviderCatalogEntry.id,
            )
            .where(CapabilityBinding.environment_id == environment.id)
            .order_by(CapabilityBinding.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    response: list[BindingRead] = []
    for binding, capability, provider in rows:
        response.append(await _to_binding_read(db, binding, capability, provider))
    return PaginatedResponse[BindingRead].create(items=response, total=total, skip=skip, limit=limit)


@router.post("/environments/{environment_id}/bindings", response_model=BindingRead)
async def upsert_binding(
    request: Request,
    environment_id: str,
    payload: BindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BindingRead:
    async def _execute() -> BindingRead:
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

    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"environment_id": environment_id, **payload.model_dump(mode="json")},
        success_status_code=status.HTTP_200_OK,
        execute=_execute,
        serialize_response=lambda binding: binding.model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.post("/bindings/{binding_id}/switchovers", response_model=SwitchoverRead)
async def create_switchover(
    request: Request,
    binding_id: str,
    payload: SwitchoverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SwitchoverPlan:
    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"binding_id": binding_id, **payload.model_dump(mode="json")},
        success_status_code=status.HTTP_200_OK,
        execute=lambda: _create_switchover_execute(
            db=db, binding_id=binding_id, payload=payload, current_user=current_user
        ),
        serialize_response=lambda switchover: SwitchoverRead.model_validate(switchover).model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.post("/switchovers/{switchover_id}/execute", response_model=SwitchoverRead)
async def execute_switchover(
    request: Request,
    switchover_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SwitchoverPlan:
    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"switchover_id": switchover_id},
        success_status_code=status.HTTP_200_OK,
        execute=lambda: _execute_switchover_execute(
            db=db, switchover_id=switchover_id, current_user=current_user
        ),
        serialize_response=lambda switchover: SwitchoverRead.model_validate(switchover).model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.post("/switchovers/{switchover_id}/rollback", response_model=SwitchoverRead)
async def rollback_switchover(
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
    return await rollback_switchover_plan(
        db,
        switchover=switchover,
        actor=current_user,
        project=project,
        environment=environment,
    )


@router.get("/bindings/{binding_id}/switchovers", response_model=PaginatedResponse[SwitchoverRead])
async def list_binding_switchovers(
    binding_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[SwitchoverRead]:
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
    total = (
        await db.execute(
            select(func.count())
            .select_from(SwitchoverPlan)
            .where(SwitchoverPlan.capability_binding_id == binding.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(SwitchoverPlan)
            .where(SwitchoverPlan.capability_binding_id == binding.id)
            .order_by(SwitchoverPlan.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return PaginatedResponse[SwitchoverRead].create(
        items=[SwitchoverRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


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


@router.get("/bindings/{binding_id}/certifications/runs", response_model=PaginatedResponse[CertificationRunRead])
async def list_certification_runs(
    binding_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[CertificationRunRead]:
    binding, environment, _project = await _load_binding_environment_and_project(
        db, binding_id=binding_id, current_user=current_user, action="bindings"
    )
    await ensure_environment_access(db, environment=environment, user_id=current_user.id, min_role=TenantRole.ADMIN)
    total = (
        await db.execute(
            select(func.count()).select_from(CertificationRun).where(CertificationRun.capability_binding_id == binding.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(CertificationRun)
            .where(CertificationRun.capability_binding_id == binding.id)
            .order_by(CertificationRun.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return PaginatedResponse[CertificationRunRead].create(
        items=[CertificationRunRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/bindings/{binding_id}/certifications/runs", response_model=CertificationRunRead, status_code=status.HTTP_201_CREATED)
async def create_binding_certification_run(
    binding_id: str,
    payload: CertificationRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CertificationRun:
    binding, environment, project = await _load_binding_environment_and_project(
        db, binding_id=binding_id, current_user=current_user, action="bindings"
    )
    switchover_plan_id = decode_id_or_404(payload.switchover_id) if payload.switchover_id else None
    run = await create_certification_run(
        db,
        binding=binding,
        actor=current_user,
        switchover_plan_id=switchover_plan_id,
        test_summary=payload.test_summary,
    )
    await record_audit_event(
        db,
        action="binding.certification_run_created",
        entity_type="certification_run",
        entity_id=str(run.id),
        actor_user_id=current_user.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"binding_id": binding.id, "switchover_plan_id": switchover_plan_id, "test_status": run.test_status.value},
    )
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/certifications/runs/{run_id}/approve", response_model=CertificationRunRead)
async def approve_binding_certification_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CertificationRun:
    run_db_id = decode_id_or_404(run_id)
    run = await db.get(CertificationRun, run_db_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification run not found")
    binding = await db.get(CapabilityBinding, run.capability_binding_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    environment = await db.get(Environment, binding.environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    project = await _authorize_environment_mutation(db, environment=environment, current_user=current_user, action="bindings")
    run = await approve_certification_run(db, run=run, actor=current_user)
    await record_audit_event(
        db,
        action="binding.certification_run_approved",
        entity_type="certification_run",
        entity_id=str(run.id),
        actor_user_id=current_user.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"binding_id": binding.id},
    )
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/certifications/runs/{run_id}/publish", response_model=CertificationRunRead)
async def publish_binding_certification_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CertificationRun:
    run_db_id = decode_id_or_404(run_id)
    run = await db.get(CertificationRun, run_db_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification run not found")
    binding = await db.get(CapabilityBinding, run.capability_binding_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    environment = await db.get(Environment, binding.environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    project = await _authorize_environment_mutation(db, environment=environment, current_user=current_user, action="bindings")
    run = await publish_certification_run(db, run=run)
    await record_audit_event(
        db,
        action="binding.certification_run_published",
        entity_type="certification_run",
        entity_id=str(run.id),
        actor_user_id=current_user.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={"binding_id": binding.id, "published_at": run.published_at.isoformat() if run.published_at else None},
    )
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/bindings/{binding_id}/status", response_model=BindingRead)
async def update_binding_status(
    request: Request,
    binding_id: str,
    payload: BindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BindingRead:
    async def _execute() -> BindingRead:
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
        binding_updated = await set_binding_status(
            db,
            binding=binding,
            status_value=payload.status,
            reason=payload.reason,
            actor=current_user,
            project=project,
            environment=environment,
        )
        return await _to_binding_read(db, binding_updated, capability, provider)

    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"binding_id": binding_id, **payload.model_dump(mode="json")},
        success_status_code=status.HTTP_200_OK,
        execute=_execute,
        serialize_response=lambda binding: binding.model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.get("/environments/{environment_id}/keys", response_model=PaginatedResponse[EnvironmentApiKeyRead])
async def list_environment_keys(
    environment_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[EnvironmentApiKeyRead]:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(db, environment=environment, user_id=current_user.id, min_role=TenantRole.ADMIN)
    total = (
        await db.execute(
            select(func.count()).select_from(EnvironmentApiKey).where(EnvironmentApiKey.environment_id == environment.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(EnvironmentApiKey)
            .where(EnvironmentApiKey.environment_id == environment.id)
            .order_by(EnvironmentApiKey.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return PaginatedResponse[EnvironmentApiKeyRead].create(
        items=[EnvironmentApiKeyRead.model_validate(row) for row in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


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


@router.get("/environments/{environment_id}/secrets", response_model=PaginatedResponse[SecretRefRead])
async def list_environment_secrets(
    environment_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[SecretRefRead]:
    environment_db_id = decode_id_or_404(environment_id)
    environment = await db.get(Environment, environment_db_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    await ensure_environment_access(db, environment=environment, user_id=current_user.id, min_role=TenantRole.ADMIN)
    total = (
        await db.execute(select(func.count()).select_from(SecretRef).where(SecretRef.environment_id == environment.id))
    ).scalar_one()
    rows = (
        await db.execute(
            select(SecretRef)
            .where(SecretRef.environment_id == environment.id)
            .order_by(SecretRef.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return PaginatedResponse[SecretRefRead].create(
        items=[SecretRefRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


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


@router.get("/projects/{project_id}/audit", response_model=PaginatedResponse[AuditLogRead])
async def list_project_audit_logs(
    project_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[AuditLogRead]:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.ADMIN)
    rows, total = await query_audit_logs(db, project_id=project.id, skip=skip, limit=limit)
    return PaginatedResponse[AuditLogRead].create(
        items=[AuditLogRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/projects/{project_id}/audit/query", response_model=PaginatedResponse[AuditLogRead])
async def query_project_audit_logs(
    project_id: str,
    actor_user_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[AuditLogRead]:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.ADMIN)
    actor_db_id = decode_id_or_404(actor_user_id) if actor_user_id else None
    rows, total = await query_audit_logs(
        db,
        project_id=project.id,
        actor_user_id=actor_db_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_ts=from_ts,
        to_ts=to_ts,
        skip=skip,
        limit=limit,
    )
    return PaginatedResponse[AuditLogRead].create(
        items=[AuditLogRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/projects/{project_id}/audit/export", response_model=AuditExportRead)
async def export_project_audit_logs(
    project_id: str,
    export_format: str = Query(default="json", pattern="^(json|csv)$"),
    actor_user_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditExportRead:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.ADMIN)
    actor_db_id = decode_id_or_404(actor_user_id) if actor_user_id else None
    rows, total = await query_audit_logs(
        db,
        project_id=project.id,
        actor_user_id=actor_db_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_ts=from_ts,
        to_ts=to_ts,
        skip=0,
        limit=10_000,
    )
    data = serialize_audit_export(rows, export_format=export_format)  # type: ignore[arg-type]
    return AuditExportRead(export_format=export_format, total=total, data=data)


@router.get("/environments/{environment_id}/compliance/evidence", response_model=ComplianceEvidenceBundleRead)
async def get_environment_compliance_evidence(
    environment_id: str,
    scope: str = Query(default="privileged", pattern="^(privileged|migration)$"),
    export_format: str = Query(default="json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComplianceEvidenceBundleRead:
    environment = await _load_environment_or_404(db, environment_id)
    await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="migrations" if scope == "migration" else "bindings",
    )
    rows, _total = await query_audit_logs(db, environment_id=environment.id, skip=0, limit=10_000)
    if scope == "migration":
        filtered = [row for row in rows if row.action.startswith("migration.")]
    else:
        filtered = [
            row
            for row in rows
            if row.action.startswith(("binding.", "secret.", "switchover.", "webhook.", "environment.", "project.lifecycle"))
        ]
    bundle = build_compliance_evidence_bundle(
        filtered,
        export_format=export_format,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        signing_key=settings.SECRET_KEY,
    )
    return ComplianceEvidenceBundleRead(**bundle)


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


@router.get("/projects/{project_id}/usage", response_model=PaginatedResponse[UsageMeterRead])
async def get_project_usage(
    project_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[UsageMeterRead]:
    project_db_id = decode_id_or_404(project_id)
    project = await db.get(Project, project_db_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await require_project_access(db, project=project, user_id=current_user.id, min_role=TenantRole.ADMIN)
    environment_ids = (
        await db.execute(select(Environment.id).where(Environment.project_id == project.id))
    ).scalars().all()
    if not environment_ids:
        return PaginatedResponse[UsageMeterRead].create(items=[], total=0, skip=skip, limit=limit)
    total = (
        await db.execute(
            select(func.count()).select_from(UsageMeter).where(UsageMeter.environment_id.in_(environment_ids))
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(UsageMeter)
            .where(UsageMeter.environment_id.in_(environment_ids))
            .order_by(UsageMeter.capability_key.asc(), UsageMeter.metric_key.asc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return PaginatedResponse[UsageMeterRead].create(
        items=[UsageMeterRead.model_validate(item) for item in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


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
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="webhook_drain",
    )
    drained_count = await drain_due_webhook_jobs(limit=limit, environment_id=environment.id)
    await record_audit_event(
        db,
        action="webhook.drain_triggered",
        entity_type="environment",
        entity_id=str(environment.id),
        actor_user_id=current_user.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={
            "limit": limit,
            "drained_count": drained_count,
            "reason": "drained" if drained_count else "no_due_jobs",
            "outcome": "allowed",
        },
    )
    await db.commit()
    return WebhookDrainResult(
        triggered=True,
        drained_count=drained_count,
        reason="drained" if drained_count else "no_due_jobs",
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
    project = await _authorize_environment_mutation(
        db,
        environment=environment,
        current_user=current_user,
        action="webhook_recover",
    )
    recovery = await replay_dead_letter_webhook_jobs(db, limit=limit)
    await record_audit_event(
        db,
        action="webhook.recover_triggered",
        entity_type="environment",
        entity_id=str(environment.id),
        actor_user_id=current_user.id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        environment_id=environment.id,
        payload={
            "limit": limit,
            "requeued_jobs": recovery.requeued_jobs,
            "scanned_failed_jobs": recovery.scanned_failed_jobs,
            "skipped_jobs": recovery.skipped_jobs,
            "reasons": recovery.reasons,
            "outcome": "allowed",
        },
    )
    await db.commit()
    return WebhookRecoveryResult(
        scanned_failed_jobs=recovery.scanned_failed_jobs,
        requeued_jobs=recovery.requeued_jobs,
        exhausted_job_ids=[encode_id(item_id) for item_id in recovery.exhausted_job_ids],
        skipped_jobs=recovery.skipped_jobs,
        skipped_job_ids=[encode_id(item_id) for item_id in recovery.skipped_job_ids],
        reasons=recovery.reasons,
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
    refreshed = await refresh_migration_reconciliation_state(db, migration=migration)
    return MigrationRead(
        id=refreshed.id or 0,
        environment_id=refreshed.environment_id,
        namespace_id=refreshed.namespace_id,
        table_definition_id=refreshed.table_definition_id,
        version=refreshed.version,
        status=refreshed.status,
        reconciliation_status=refreshed.reconciliation_status,
        drift_severity=refreshed.drift_severity,
        affected_entities=refreshed.drift_entities_json,
        reconcile_attempt_count=refreshed.reconcile_attempt_count,
        reconcile_error_text=refreshed.reconcile_error_text,
        last_reconciled_at=refreshed.last_reconciled_at,
        applied_sql=refreshed.applied_sql,
        created_at=refreshed.created_at,
    )

@router.get("/environments/{environment_id}/migrations", response_model=PaginatedResponse[MigrationRead])
async def list_environment_migrations(
    environment_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[MigrationRead]:
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
    total = (
        await db.execute(
            select(func.count()).select_from(SchemaMigration).where(SchemaMigration.environment_id == environment.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(SchemaMigration)
            .where(SchemaMigration.environment_id == environment.id)
            .order_by(SchemaMigration.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    response = [await _to_migration_read(db, row) for row in rows]
    await db.commit()
    return PaginatedResponse[MigrationRead].create(items=response, total=total, skip=skip, limit=limit)


@router.post(
    "/environments/{environment_id}/migrations/{migration_id}/apply",
    response_model=MigrationRead,
)
async def apply_environment_migration(
    request: Request,
    environment_id: str,
    migration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MigrationRead:
    async def _execute() -> MigrationRead:
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

    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"environment_id": environment_id, "migration_id": migration_id},
        success_status_code=status.HTTP_200_OK,
        execute=_execute,
        serialize_response=lambda migration: migration.model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.post(
    "/environments/{environment_id}/migrations/{migration_id}/retry",
    response_model=MigrationRollbackResult,
)
async def retry_environment_migration(
    request: Request,
    environment_id: str,
    migration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MigrationRollbackResult:
    async def _execute() -> MigrationRollbackResult:
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
        await record_audit_event(
            db,
            action="migration.retry_requested",
            entity_type="schema_migration",
            entity_id=str(migration.id),
            actor_user_id=current_user.id,
            tenant_id=project.tenant_id,
            project_id=project.id,
            environment_id=environment.id,
            payload={"version": migration.version, "outcome": "allowed"},
        )
        await db.commit()
        migration_read = await _to_migration_read(db, migration)
        return MigrationRollbackResult(
            migration=migration_read,
            rollback_sql=f"-- retry for migration {migration.version}",
            rollback_status="requested",
        )

    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"environment_id": environment_id, "migration_id": migration_id},
        success_status_code=status.HTTP_200_OK,
        execute=_execute,
        serialize_response=lambda migration_result: migration_result.model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


@router.post(
    "/environments/{environment_id}/migrations/{migration_id}/reconcile",
    response_model=MigrationRead,
)
async def reconcile_environment_migration(
    request: Request,
    environment_id: str,
    migration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MigrationRead:
    async def _execute() -> MigrationRead:
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
        refreshed = await execute_migration_reconciliation(db, migration=migration)
        await record_audit_event(
            db,
            action="migration.reconciled",
            entity_type="schema_migration",
            entity_id=str(refreshed.id),
            actor_user_id=current_user.id,
            tenant_id=project.tenant_id,
            project_id=project.id,
            environment_id=environment.id,
            payload={
                "version": refreshed.version,
                "reconciliation_status": refreshed.reconciliation_status,
                "outcome": "allowed",
            },
        )
        await db.commit()
        return await _to_migration_read(db, refreshed)

    result = await _execute_idempotent_mutation(
        request=request,
        db=db,
        current_user=current_user,
        request_payload={"environment_id": environment_id, "migration_id": migration_id},
        success_status_code=status.HTTP_200_OK,
        execute=_execute,
        serialize_response=lambda migration: migration.model_dump(mode="json"),
    )
    if isinstance(result, JSONResponse):
        return result
    return result


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
