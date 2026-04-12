from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import ISODateTime, PostBaseContractModel
from src.postbase.platform.contracts import ProviderAdapter


class FunctionCreateRequest(PostBaseContractModel):
    slug: str
    name: str
    handler_type: str = "echo"
    runtime_profile: str = "celery-runtime"
    config_json: dict[str, Any] = Field(default_factory=dict)
    env_policy_json: dict[str, Any] = Field(default_factory=dict)


class FunctionRead(PostBaseContractModel):
    id: int
    slug: str
    name: str
    handler_type: str
    runtime_profile: str
    config_json: dict[str, Any]
    env_policy_json: dict[str, Any]
    is_active: bool


class FunctionInvokeRequest(PostBaseContractModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    invocation_type: str = "sync"
    timeout_ms: int | None = None
    cancel_requested: bool = False


class ExecutionRead(PostBaseContractModel):
    id: int
    function_definition_id: int
    invocation_type: str
    idempotency_key: str | None
    correlation_id: str
    replay_of_execution_id: int | None
    retry_of_execution_id: int | None
    retry_count: int
    timeout_ms: int | None
    cancel_requested: bool
    schedule_id: int | None
    trigger_source: str
    execution_metadata_json: dict[str, Any]
    status: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    started_at: ISODateTime
    completed_at: ISODateTime | None
    error_text: str = ""
    log_excerpt: str = ""


class FunctionScheduleCreateRequest(PostBaseContractModel):
    name: str
    schedule_type: str = "cron"
    cron_expr: str | None = None
    interval_seconds: int | None = None
    timezone: str = "UTC"
    misfire_grace_seconds: int = 60
    max_jitter_seconds: int = 0


class FunctionScheduleRead(PostBaseContractModel):
    id: int
    function_definition_id: int
    name: str
    schedule_type: str
    cron_expr: str | None
    interval_seconds: int | None
    timezone: str
    status: str
    misfire_grace_seconds: int
    max_jitter_seconds: int
    last_scheduled_at: ISODateTime | None
    last_run_at: ISODateTime | None
    next_run_at: ISODateTime | None
    run_count: int
    last_execution_id: int | None
    created_at: ISODateTime
    updated_at: ISODateTime


class FunctionDeploymentRevisionRead(PostBaseContractModel):
    id: int
    function_definition_id: int
    revision: int
    source_ref: str
    handler_type: str
    runtime_profile: str
    config_json: dict[str, Any]
    env_policy_json: dict[str, Any]
    deployed_by_user_id: int | None
    created_at: ISODateTime


class FunctionDeploymentEventRead(PostBaseContractModel):
    id: int
    function_definition_id: int
    revision_id: int | None
    event_type: str
    actor_user_id: int | None
    metadata_json: dict[str, Any]
    created_at: ISODateTime


class FunctionsProvider(ProviderAdapter, Protocol):
    async def create_function(self, context, payload: FunctionCreateRequest) -> FunctionRead:
        ...

    async def list_functions(self, context, *, skip: int, limit: int) -> PaginatedResponse[FunctionRead]:
        ...

    async def invoke(
        self,
        context,
        function_id: int,
        payload: FunctionInvokeRequest,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        retry_of_execution_id: int | None = None,
    ) -> ExecutionRead:
        ...

    async def list_executions(
        self,
        context,
        function_id: int,
        *,
        skip: int,
        limit: int,
    ) -> PaginatedResponse[ExecutionRead]:
        ...

    async def create_schedule(
        self, context, function_id: int, payload: FunctionScheduleCreateRequest
    ) -> FunctionScheduleRead:
        ...

    async def list_schedules(self, context, function_id: int, *, skip: int, limit: int) -> PaginatedResponse[FunctionScheduleRead]:
        ...

    async def pause_schedule(self, context, function_id: int, schedule_id: int) -> FunctionScheduleRead:
        ...

    async def resume_schedule(self, context, function_id: int, schedule_id: int) -> FunctionScheduleRead:
        ...

    async def run_schedule_now(self, context, function_id: int, schedule_id: int) -> ExecutionRead:
        ...

    async def delete_schedule(self, context, function_id: int, schedule_id: int) -> None:
        ...

    async def list_deployment_history(
        self, context, function_id: int, *, skip: int, limit: int
    ) -> PaginatedResponse[FunctionDeploymentEventRead]:
        ...

    async def list_revisions(
        self, context, function_id: int, *, skip: int, limit: int
    ) -> PaginatedResponse[FunctionDeploymentRevisionRead]:
        ...

    async def rollback_revision(self, context, function_id: int, revision_id: int) -> FunctionRead:
        ...
