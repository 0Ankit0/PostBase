from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer

from src.apps.iam.utils.hashid import encode_id
from src.postbase.domain.enums import (
    ApiKeyRole,
    BindingStatus,
    CertificationApprovalState,
    CertificationTestStatus,
    EnvironmentStage,
    EnvironmentStatus,
    PolicyMode,
    ReadinessState,
    SwitchoverStatus,
    MigrationStatus,
)


class EncodedModel(BaseModel):
    model_config = {"from_attributes": True}

    @field_serializer("id", check_fields=False)
    def serialize_id(self, value: int) -> str:
        return encode_id(value)


class ProjectCreate(BaseModel):
    tenant_id: str
    name: str
    slug: str
    description: str = ""


class ProjectLifecycleUpdate(BaseModel):
    is_active: bool


class ProjectRead(EncodedModel):
    id: int
    tenant_id: int
    name: str
    slug: str
    description: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("tenant_id")
    def serialize_tenant_id(self, value: int) -> str:
        return encode_id(value)


class EnvironmentCreate(BaseModel):
    name: str
    slug: str
    stage: EnvironmentStage = EnvironmentStage.DEVELOPMENT
    region_preference: str | None = None


class EnvironmentLifecycleUpdate(BaseModel):
    status: EnvironmentStatus | None = None
    is_active: bool | None = None
    reason: str | None = None


class EnvironmentRead(EncodedModel):
    id: int
    project_id: int
    name: str
    slug: str
    stage: EnvironmentStage
    region_preference: str | None
    status: EnvironmentStatus
    readiness_state: ReadinessState
    readiness_detail: str
    last_validated_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("project_id")
    def serialize_project_id(self, value: int) -> str:
        return encode_id(value)


class ProviderCatalogRead(EncodedModel):
    id: int
    capability_key: str
    provider_key: str
    adapter_version: str
    certification_state: str
    metadata_json: dict[str, Any]


class BindingCreate(BaseModel):
    capability_key: str
    provider_key: str
    config_json: dict[str, Any] = {}
    secret_ref_ids: list[str] = []
    region: str | None = None


class BindingRead(EncodedModel):
    id: int
    environment_id: int
    capability_key: str
    provider_key: str
    adapter_version: str
    status: BindingStatus
    readiness_detail: str
    linked_secret_ref_ids: list[str]
    supersedes_binding_id: str | None
    last_transition_actor_user_id: str | None
    last_transition_reason: str
    last_transition_at: datetime | None
    region: str | None
    config_json: dict[str, Any]

    @field_serializer("environment_id")
    def serialize_environment_id(self, value: int) -> str:
        return encode_id(value)


class BindingStatusUpdate(BaseModel):
    status: BindingStatus
    reason: str | None = None


class SwitchoverCreate(BaseModel):
    target_provider_key: str
    strategy: str = "cutover"
    retirement_strategy: str = "manual"
    canary_traffic_percent: int = 0
    canary_health_checkpoint_count: int = 1
    auto_abort_error_rate: float = 0.1
    simulated_canary_error_rate: float | None = None


class SwitchoverRead(EncodedModel):
    id: int
    capability_binding_id: int
    target_provider_catalog_entry_id: int
    strategy: str
    retirement_strategy: str
    status: SwitchoverStatus
    execution_detail: str
    execution_state_json: dict[str, object]
    canary_traffic_percent: int
    canary_health_checkpoint_count: int
    auto_abort_error_rate: float
    created_at: datetime
    completed_at: datetime | None

    @field_serializer("capability_binding_id", "target_provider_catalog_entry_id")
    def serialize_related_id(self, value: int) -> str:
        return encode_id(value)


class EnvironmentApiKeyCreate(BaseModel):
    name: str
    role: ApiKeyRole = ApiKeyRole.ANON


class EnvironmentApiKeyRead(EncodedModel):
    id: int
    environment_id: int
    name: str
    role: ApiKeyRole
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None

    @field_serializer("environment_id")
    def serialize_environment_id(self, value: int) -> str:
        return encode_id(value)


class EnvironmentApiKeyIssued(BaseModel):
    api_key: EnvironmentApiKeyRead
    plaintext_key: str


class SecretRefCreate(BaseModel):
    name: str
    provider_key: str
    secret_kind: str
    secret_value: str


class SecretRotate(BaseModel):
    secret_value: str


class SecretRotateResult(BaseModel):
    secret: "SecretRefRead"
    impacted_binding_ids: list[str]
    post_rotation_health_check: list["ProviderHealthRead"]
    rollback_ready: bool


class SecretRefRead(EncodedModel):
    id: int
    environment_id: int
    name: str
    provider_key: str
    secret_kind: str
    version: int
    is_active_version: bool
    status: str
    rotated_at: datetime | None
    expires_at: datetime | None
    last_four: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("environment_id")
    def serialize_environment_id(self, value: int) -> str:
        return encode_id(value)


class CertificationRunCreate(BaseModel):
    switchover_id: str | None = None
    test_summary: str = "adapter verification requested"


class CertificationRunRead(EncodedModel):
    id: int
    capability_binding_id: int
    switchover_plan_id: int | None
    test_status: CertificationTestStatus
    approval_state: CertificationApprovalState
    test_summary: str
    evidence_refs_json: dict[str, Any]
    requested_by_user_id: int | None
    approved_by_user_id: int | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_serializer(
        "capability_binding_id",
        "switchover_plan_id",
        "requested_by_user_id",
        "approved_by_user_id",
        check_fields=False,
    )
    def serialize_related_id(self, value: int | None) -> str | None:
        return encode_id(value) if value else None


class AuditLogRead(EncodedModel):
    id: int
    action: str
    entity_type: str
    entity_id: str
    payload_json: dict[str, Any]
    created_at: datetime


class ProviderHealthRead(BaseModel):
    capability_key: str
    provider_key: str
    adapter_version: str
    ready: bool
    detail: str


class CapabilityHealthReport(BaseModel):
    environment_id: str
    bindings: list[BindingRead]
    provider_health: list[ProviderHealthRead]
    overall_ready: bool
    degraded_capabilities: list[str]


class UsageMeterRead(EncodedModel):
    id: int
    environment_id: int
    capability_key: str
    metric_key: str
    value: float
    measured_at: datetime

    @field_serializer("environment_id")
    def serialize_environment_id(self, value: int) -> str:
        return encode_id(value)


class NamespaceCreate(BaseModel):
    name: str


class NamespaceRead(EncodedModel):
    id: int
    environment_id: int
    name: str
    physical_schema: str
    status: str
    created_at: datetime

    @field_serializer("environment_id")
    def serialize_environment_id(self, value: int) -> str:
        return encode_id(value)


class ColumnDefinition(BaseModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False


class TableCreate(BaseModel):
    table_name: str
    columns: list[ColumnDefinition]
    policy_mode: PolicyMode = PolicyMode.PUBLIC
    owner_column: str | None = None


class TableRead(EncodedModel):
    id: int
    namespace_id: int
    table_name: str
    columns_json: list[dict[str, Any]]
    policy_mode: PolicyMode
    owner_column: str | None
    status: str

    @field_serializer("namespace_id")
    def serialize_namespace_id(self, value: int) -> str:
        return encode_id(value)


class MigrationRead(EncodedModel):
    id: int
    environment_id: int
    namespace_id: int
    table_definition_id: int | None
    version: str
    status: MigrationStatus
    reconciliation_status: str
    drift_severity: str
    affected_entities: list[str]
    reconcile_attempt_count: int
    reconcile_error_text: str
    last_reconciled_at: datetime | None
    applied_sql: str
    created_at: datetime

    @field_serializer("environment_id", "namespace_id", "table_definition_id")
    def serialize_related_ids(self, value: int | None) -> str | None:
        if value is None:
            return None
        return encode_id(value)


class MigrationRollbackResult(BaseModel):
    migration: MigrationRead
    rollback_sql: str
    rollback_status: str


class WebhookRecoveryResult(BaseModel):
    scanned_failed_jobs: int
    requeued_jobs: int
    exhausted_job_ids: list[str]
    skipped_jobs: int
    skipped_job_ids: list[str]
    reasons: dict[str, int]


class OperationsChecklistItem(BaseModel):
    item: str
    completed: bool


class WebhookDrainResult(BaseModel):
    triggered: bool
    drained_count: int
    reason: str
    checklist: list[OperationsChecklistItem]


class EnvironmentOverviewRead(BaseModel):
    environment_id: str
    stage: EnvironmentStage
    status: EnvironmentStatus
    readiness_state: ReadinessState
    readiness_detail: str
    active_bindings: int
    degraded_bindings: int
    recent_switchovers: int
    pending_migrations: int
    drifted_migrations: int
    secret_count: int
    key_count: int
    usage_points_total: float
    recent_audit_events: int
    quota_state: str
    quota_warning_triggered: bool
    quota_soft_limited: bool
    quota_hard_limited: bool
    quota_utilization: float
    degradation_mode: str


class ProjectOverviewRead(BaseModel):
    project_id: str
    environment_count: int
    active_environment_count: int
    active_bindings: int
    degraded_bindings: int
    secret_count: int
    usage_points_total: float
    recent_audit_events: int
    environments: list[EnvironmentOverviewRead]


class AuditExportRead(BaseModel):
    export_format: str
    total: int
    data: str


class ComplianceEvidenceBundleRead(BaseModel):
    scope: str
    export_format: str
    record_count: int
    generated_at: str
    hash_sha256: str
    signature_hmac_sha256: str
    data: str
