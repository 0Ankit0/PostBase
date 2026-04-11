from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.apps.core.schemas import PaginatedResponse
from src.postbase.platform.contracts import ProviderAdapter


class FunctionCreateRequest(BaseModel):
    slug: str
    name: str
    handler_type: str = "echo"
    runtime_profile: str = "celery-runtime"
    config_json: dict[str, Any] = Field(default_factory=dict)


class FunctionRead(BaseModel):
    id: int
    slug: str
    name: str
    handler_type: str
    runtime_profile: str
    config_json: dict[str, Any]
    is_active: bool


class FunctionInvokeRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    invocation_type: str = "sync"
    timeout_ms: int | None = None
    cancel_requested: bool = False


class ExecutionRead(BaseModel):
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
    status: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    error_text: str
    started_at: datetime
    completed_at: datetime | None
    log_excerpt: str


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
