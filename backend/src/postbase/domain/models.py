from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, Index, String, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from src.postbase.domain.enums import (
    ApiKeyRole,
    BindingStatus,
    EnvironmentStatus,
    EnvironmentStage,
    MigrationStatus,
    PolicyMode,
    ProviderCertificationState,
    ReadinessState,
    SecretStatus,
    SwitchoverStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    __tablename__ = "postbase_project"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_postbase_project_tenant_slug"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    name: str = Field(max_length=120)
    slug: str = Field(max_length=63, index=True)
    description: str = Field(default="", max_length=500)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Environment(SQLModel, table=True):
    __tablename__ = "postbase_environment"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_postbase_environment_project_slug"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="postbase_project.id", index=True)
    name: str = Field(max_length=120)
    slug: str = Field(max_length=63)
    stage: EnvironmentStage = Field(default=EnvironmentStage.DEVELOPMENT)
    region_preference: str | None = Field(default=None, max_length=64)
    status: EnvironmentStatus = Field(default=EnvironmentStatus.ACTIVE)
    readiness_state: ReadinessState = Field(default=ReadinessState.READY)
    readiness_detail: str = Field(default="", max_length=500)
    last_validated_at: datetime | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CapabilityType(SQLModel, table=True):
    __tablename__ = "postbase_capability_type"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True, max_length=32)
    facade_version: str = Field(default="v1", max_length=20)
    description: str = Field(default="", max_length=300)


class ProviderCatalogEntry(SQLModel, table=True):
    __tablename__ = "postbase_provider_catalog_entry"
    __table_args__ = (
        UniqueConstraint(
            "capability_type_id",
            "provider_key",
            "adapter_version",
            name="uq_postbase_provider_catalog_entry",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    capability_type_id: int = Field(foreign_key="postbase_capability_type.id", index=True)
    provider_key: str = Field(index=True, max_length=64)
    adapter_version: str = Field(default="1.0.0", max_length=20)
    certification_state: ProviderCertificationState = Field(
        default=ProviderCertificationState.CERTIFIED
    )
    is_enabled: bool = Field(default=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    created_at: datetime = Field(default_factory=utcnow)


class CapabilityBinding(SQLModel, table=True):
    __tablename__ = "postbase_capability_binding"
    __table_args__ = (
        Index(
            "uq_postbase_capability_binding_active_per_capability_env",
            "environment_id",
            "capability_type_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    capability_type_id: int = Field(foreign_key="postbase_capability_type.id", index=True)
    provider_catalog_entry_id: int = Field(
        foreign_key="postbase_provider_catalog_entry.id",
        index=True,
    )
    status: BindingStatus = Field(default=BindingStatus.PENDING_VALIDATION)
    readiness_detail: str = Field(default="", max_length=500)
    region: str | None = Field(default=None, max_length=64)
    supersedes_binding_id: int | None = Field(default=None, foreign_key="postbase_capability_binding.id")
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    last_transition_actor_user_id: int | None = Field(default=None, index=True)
    last_transition_reason: str = Field(default="", max_length=255)
    last_transition_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SecretRef(SQLModel, table=True):
    __tablename__ = "postbase_secret_ref"
    __table_args__ = (
        UniqueConstraint("environment_id", "name", "version", name="uq_postbase_secret_ref_env_name_version"),
        Index(
            "uq_postbase_secret_ref_active_version_per_name",
            "environment_id",
            "name",
            unique=True,
            sqlite_where=text("is_active_version = 1"),
            postgresql_where=text("is_active_version = true"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    name: str = Field(max_length=100)
    provider_key: str = Field(max_length=64)
    secret_kind: str = Field(max_length=64)
    version: int = Field(default=1)
    is_active_version: bool = Field(default=True)
    status: SecretStatus = Field(default=SecretStatus.ACTIVE)
    rotated_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    last_four: str = Field(default="", max_length=4)
    encrypted_value: str = Field(default="")
    value_hash: str = Field(max_length=128)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EnvironmentApiKey(SQLModel, table=True):
    __tablename__ = "postbase_environment_api_key"
    __table_args__ = (
        UniqueConstraint("key_prefix", name="uq_postbase_environment_api_key_prefix"),
    )

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    name: str = Field(max_length=100)
    role: ApiKeyRole = Field(default=ApiKeyRole.ANON)
    key_prefix: str = Field(max_length=16, index=True)
    hashed_secret: str = Field(max_length=128)
    is_active: bool = Field(default=True)
    last_used_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class BindingSecretRef(SQLModel, table=True):
    __tablename__ = "postbase_binding_secret_ref"
    __table_args__ = (
        UniqueConstraint("binding_id", "secret_ref_id", name="uq_postbase_binding_secret_ref"),
    )

    id: int | None = Field(default=None, primary_key=True)
    binding_id: int = Field(foreign_key="postbase_capability_binding.id", index=True)
    secret_ref_id: int = Field(foreign_key="postbase_secret_ref.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "postbase_audit_log"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenant.id", index=True)
    project_id: int | None = Field(default=None, foreign_key="postbase_project.id", index=True)
    environment_id: int | None = Field(default=None, foreign_key="postbase_environment.id", index=True)
    actor_user_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    action: str = Field(max_length=120, index=True)
    entity_type: str = Field(max_length=80)
    entity_id: str = Field(max_length=80)
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    created_at: datetime = Field(default_factory=utcnow, index=True)


class UsageMeter(SQLModel, table=True):
    __tablename__ = "postbase_usage_meter"

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    capability_key: str = Field(max_length=32, index=True)
    metric_key: str = Field(max_length=64)
    value: float = Field(default=0.0)
    measured_at: datetime = Field(default_factory=utcnow, index=True)


class IdempotencyRecord(SQLModel, table=True):
    __tablename__ = "postbase_idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            "actor_user_id",
            "endpoint_fingerprint",
            name="uq_postbase_idempotency_key_actor_endpoint",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    idempotency_key: str = Field(max_length=255, index=True)
    actor_user_id: int = Field(foreign_key="user.id", index=True)
    endpoint_fingerprint: str = Field(max_length=255)
    request_hash: str = Field(max_length=128)
    response_status_code: int | None = Field(default=None)
    response_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class SwitchoverPlan(SQLModel, table=True):
    __tablename__ = "postbase_switchover_plan"

    id: int | None = Field(default=None, primary_key=True)
    capability_binding_id: int = Field(
        foreign_key="postbase_capability_binding.id",
        index=True,
    )
    target_provider_catalog_entry_id: int = Field(
        foreign_key="postbase_provider_catalog_entry.id",
        index=True,
    )
    strategy: str = Field(default="cutover", max_length=64)
    retirement_strategy: str = Field(default="manual", sa_column=Column(String(16), nullable=False, default="manual"))
    status: SwitchoverStatus = Field(default=SwitchoverStatus.PENDING)
    execution_detail: str = Field(default="")
    execution_state_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    requested_by_user_id: int | None = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = Field(default=None)


class AuthUser(SQLModel, table=True):
    __tablename__ = "postbase_auth_user"
    __table_args__ = (
        UniqueConstraint("project_id", "email", name="uq_postbase_auth_user_project_email"),
        UniqueConstraint("project_id", "username", name="uq_postbase_auth_user_project_username"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="postbase_project.id", index=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    username: str = Field(max_length=60)
    email: str = Field(max_length=255)
    password_hash: str = Field(max_length=255)
    is_active: bool = Field(default=True)
    is_confirmed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SessionRecord(SQLModel, table=True):
    __tablename__ = "postbase_session_record"
    __table_args__ = (
        UniqueConstraint("access_jti", name="uq_postbase_session_record_access_jti"),
        UniqueConstraint("refresh_jti", name="uq_postbase_session_record_refresh_jti"),
    )

    id: int | None = Field(default=None, primary_key=True)
    auth_user_id: int = Field(foreign_key="postbase_auth_user.id", index=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    access_jti: str = Field(max_length=80)
    refresh_jti: str = Field(max_length=80)
    refresh_expires_at: datetime = Field()
    last_seen_at: datetime = Field(default_factory=utcnow)
    revoked_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class DataNamespace(SQLModel, table=True):
    __tablename__ = "postbase_data_namespace"
    __table_args__ = (
        UniqueConstraint("environment_id", "name", name="uq_postbase_data_namespace_env_name"),
    )

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    name: str = Field(max_length=63)
    physical_schema: str = Field(max_length=63, index=True)
    status: str = Field(default="active", max_length=32)
    created_at: datetime = Field(default_factory=utcnow)


class TableDefinition(SQLModel, table=True):
    __tablename__ = "postbase_table_definition"
    __table_args__ = (
        UniqueConstraint("namespace_id", "table_name", name="uq_postbase_table_definition"),
    )

    id: int | None = Field(default=None, primary_key=True)
    namespace_id: int = Field(foreign_key="postbase_data_namespace.id", index=True)
    table_name: str = Field(max_length=63)
    columns_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, default=list),
    )
    policy_mode: PolicyMode = Field(default=PolicyMode.PUBLIC)
    owner_column: str | None = Field(default=None, max_length=63)
    status: str = Field(default="active", max_length=32)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PolicyDefinition(SQLModel, table=True):
    __tablename__ = "postbase_policy_definition"

    id: int | None = Field(default=None, primary_key=True)
    table_definition_id: int = Field(
        foreign_key="postbase_table_definition.id",
        index=True,
    )
    policy_mode: PolicyMode = Field(default=PolicyMode.PUBLIC)
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    created_at: datetime = Field(default_factory=utcnow)


class SchemaMigration(SQLModel, table=True):
    __tablename__ = "postbase_schema_migration"

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    namespace_id: int = Field(foreign_key="postbase_data_namespace.id", index=True)
    table_definition_id: int | None = Field(
        default=None,
        foreign_key="postbase_table_definition.id",
        index=True,
    )
    version: str = Field(max_length=40)
    status: MigrationStatus = Field(default=MigrationStatus.APPLIED, index=True)
    reconciliation_status: str = Field(default="pending_apply", max_length=32, index=True)
    drift_severity: str = Field(default="none", max_length=16)
    drift_entities_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, default=list),
    )
    reconcile_attempt_count: int = Field(default=0)
    reconcile_error_text: str = Field(default="")
    last_reconciled_at: datetime | None = Field(default=None)
    applied_sql: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class SchemaMigrationExecution(SQLModel, table=True):
    __tablename__ = "postbase_schema_migration_execution"

    id: int | None = Field(default=None, primary_key=True)
    migration_id: int = Field(foreign_key="postbase_schema_migration.id", index=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    status: MigrationStatus = Field(default=MigrationStatus.PENDING, index=True)
    error_text: str = Field(default="")
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = Field(default=None)


class FileObject(SQLModel, table=True):
    __tablename__ = "postbase_file_object"

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    namespace: str = Field(default="default", max_length=63)
    bucket_key: str = Field(default="default", max_length=63, index=True)
    path: str = Field(max_length=255, index=True)
    filename: str = Field(max_length=255)
    content_type: str = Field(default="application/octet-stream", max_length=120)
    size_bytes: int = Field(default=0)
    provider_object_ref: str = Field(max_length=255)
    owner_auth_user_id: int | None = Field(default=None, foreign_key="postbase_auth_user.id", index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    created_at: datetime = Field(default_factory=utcnow)


class FunctionDefinition(SQLModel, table=True):
    __tablename__ = "postbase_function_definition"
    __table_args__ = (
        UniqueConstraint("environment_id", "slug", name="uq_postbase_function_definition_env_slug"),
    )

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    slug: str = Field(max_length=63, index=True)
    name: str = Field(max_length=120)
    runtime_profile: str = Field(default="celery-runtime", max_length=80)
    handler_type: str = Field(default="echo", max_length=40)
    code_ref: str = Field(default="", max_length=255)
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ExecutionRecord(SQLModel, table=True):
    __tablename__ = "postbase_execution_record"

    id: int | None = Field(default=None, primary_key=True)
    function_definition_id: int = Field(foreign_key="postbase_function_definition.id", index=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    invocation_type: str = Field(default="sync", max_length=20)
    idempotency_key: str | None = Field(default=None, max_length=120, index=True)
    correlation_id: str = Field(default="", max_length=120, index=True)
    replay_of_execution_id: int | None = Field(default=None, foreign_key="postbase_execution_record.id")
    retry_of_execution_id: int | None = Field(default=None, foreign_key="postbase_execution_record.id")
    retry_count: int = Field(default=0)
    timeout_ms: int | None = Field(default=None)
    cancel_requested: bool = Field(default=False)
    log_excerpt: str = Field(default="")
    status: str = Field(default="completed", max_length=32, index=True)
    input_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    output_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    error_text: str = Field(default="")
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = Field(default=None)


class EventChannel(SQLModel, table=True):
    __tablename__ = "postbase_event_channel"
    __table_args__ = (
        UniqueConstraint("environment_id", "channel_key", name="uq_postbase_event_channel_env_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    environment_id: int = Field(foreign_key="postbase_environment.id", index=True)
    channel_key: str = Field(max_length=80, index=True)
    description: str = Field(default="", max_length=255)
    created_at: datetime = Field(default_factory=utcnow)


class Subscription(SQLModel, table=True):
    __tablename__ = "postbase_subscription"

    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="postbase_event_channel.id", index=True)
    target_type: str = Field(max_length=32)
    target_ref: str = Field(max_length=255)
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)


class DeliveryRecord(SQLModel, table=True):
    __tablename__ = "postbase_delivery_record"

    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="postbase_event_channel.id", index=True)
    subscription_id: int | None = Field(default=None, foreign_key="postbase_subscription.id", index=True)
    event_name: str = Field(max_length=120, index=True)
    status: str = Field(default="delivered", max_length=32)
    attempt_count: int = Field(default=1)
    delivered_at: datetime | None = Field(default=None)
    error_text: str = Field(default="")
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    attempted_at: datetime = Field(default_factory=utcnow)


class WebhookDeliveryJob(SQLModel, table=True):
    __tablename__ = "postbase_webhook_delivery_job"

    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="postbase_event_channel.id", index=True)
    subscription_id: int = Field(foreign_key="postbase_subscription.id", index=True)
    event_name: str = Field(max_length=120, index=True)
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    target_ref: str = Field(max_length=255)
    status: str = Field(default="pending", max_length=32)
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    error_text: str = Field(default="")
    latest_response_code: int | None = Field(default=None)
    latest_latency_ms: int | None = Field(default=None)
    attempt_history_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, default=list),
    )
    next_attempt_at: datetime | None = Field(default=None, index=True)
    delivered_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class DeadLetterWebhookDelivery(SQLModel, table=True):
    __tablename__ = "postbase_dead_letter_webhook_delivery"

    id: int | None = Field(default=None, primary_key=True)
    webhook_delivery_job_id: int = Field(
        foreign_key="postbase_webhook_delivery_job.id",
        index=True,
        unique=True,
    )
    channel_id: int = Field(foreign_key="postbase_event_channel.id", index=True)
    subscription_id: int = Field(foreign_key="postbase_subscription.id", index=True)
    event_name: str = Field(max_length=120, index=True)
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    target_ref: str = Field(max_length=255)
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    latest_response_code: int | None = Field(default=None)
    latest_latency_ms: int | None = Field(default=None)
    error_text: str = Field(default="")
    attempt_history_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, default=list),
    )
    dead_letter_state: str = Field(default="active", max_length=32)
    dead_lettered_at: datetime = Field(default_factory=utcnow, index=True)
    replayed_at: datetime | None = Field(default=None)
