from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class FunctionCreateRequest(BaseModel):
    slug: str
    name: str
    handler_type: str = "echo"
    runtime_profile: str = "celery-runtime"
    config_json: dict[str, Any] = {}


class FunctionRead(BaseModel):
    id: int
    slug: str
    name: str
    handler_type: str
    runtime_profile: str
    config_json: dict[str, Any]
    is_active: bool


class FunctionInvokeRequest(BaseModel):
    payload: dict[str, Any] = {}
    invocation_type: str = "sync"


class ExecutionRead(BaseModel):
    id: int
    function_definition_id: int
    invocation_type: str
    status: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    error_text: str


class FunctionsProvider(Protocol):
    async def create_function(self, context, payload: FunctionCreateRequest) -> FunctionRead:
        ...

    async def list_functions(self, context) -> list[FunctionRead]:
        ...

    async def invoke(self, context, function_id: int, payload: FunctionInvokeRequest) -> ExecutionRead:
        ...

    async def list_executions(self, context, function_id: int) -> list[ExecutionRead]:
        ...
