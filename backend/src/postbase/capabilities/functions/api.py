from fastapi import APIRouter, Depends

from src.postbase.capabilities.functions.contracts import (
    ExecutionRead,
    FunctionCreateRequest,
    FunctionInvokeRequest,
    FunctionRead,
)
from src.postbase.capabilities.functions.dependencies import get_access_context, get_functions_provider

router = APIRouter(prefix="/functions", tags=["postbase-functions"])


@router.post("", response_model=FunctionRead)
async def create_function(
    payload: FunctionCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> FunctionRead:
    return await provider.create_function(context, payload)


@router.get("", response_model=list[FunctionRead])
async def list_functions(
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> list[FunctionRead]:
    return await provider.list_functions(context)


@router.post("/{function_id}/invoke", response_model=ExecutionRead)
async def invoke_function(
    function_id: int,
    payload: FunctionInvokeRequest,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> ExecutionRead:
    return await provider.invoke(context, function_id, payload)


@router.get("/{function_id}/executions", response_model=list[ExecutionRead])
async def list_executions(
    function_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> list[ExecutionRead]:
    return await provider.list_executions(context, function_id)
