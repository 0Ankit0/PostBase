from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer

from src.apps.iam.utils.hashid import encode_id
from src.postbase.domain.enums import (
    ApiKeyRole,
    BindingStatus,
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
    region: str | None
    config_json: dict[str, Any]

    @field_serializer("environment_id")
    def serialize_environment_id(self, value: int) -> str:
        return encode_id(value)


class BindingStatusUpdate(BaseModel):
    status: BindingStatus


class SwitchoverCreate(BaseModel):
    target_provider_key: str
    strategy: str = "cutover"


class SwitchoverRead(EncodedModel):
    id: int
    capability_binding_id: int
    target_provider_catalog_entry_id: int
    strategy: str
    status: SwitchoverStatus
    execution_detail: str
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
    status: str
    last_four: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("environment_id")
    def serialize_environment_id(self, value: int) -> str:
        return encode_id(value)


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




class OperationsChecklistItem(BaseModel):
    item: str
    completed: bool


class WebhookDrainResult(BaseModel):
    triggered: bool
    drained_count: int
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
    secret_count: int
    key_count: int
    usage_points_total: float
    recent_audit_events: int


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
