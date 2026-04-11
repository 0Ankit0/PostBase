from fastapi import APIRouter, Depends, Header, Query

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import FacadeStatusResponse
from src.postbase.capabilities.functions.contracts import (
    ExecutionRead,
    FunctionCreateRequest,
    FunctionInvokeRequest,
    FunctionRead,
)
from src.postbase.capabilities.functions.dependencies import get_access_context, get_functions_facade, get_functions_provider
from src.postbase.capabilities.functions.service import FunctionsFacade

router = APIRouter(prefix="/functions", tags=["postbase-functions"])


@router.post("", response_model=FunctionRead)
async def create_function(
    payload: FunctionCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> FunctionRead:
    return await provider.create_function(context, payload)


@router.get("", response_model=PaginatedResponse[FunctionRead])
async def list_functions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> PaginatedResponse[FunctionRead]:
    return await provider.list_functions(context, skip=skip, limit=limit)


@router.post("/{function_id}/invoke", response_model=ExecutionRead)
async def invoke_function(
    function_id: int,
    payload: FunctionInvokeRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    retry_of_execution_id: int | None = Header(default=None, alias="X-Retry-Of-Execution-Id"),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> ExecutionRead:
    return await provider.invoke(
        context,
        function_id,
        payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        retry_of_execution_id=retry_of_execution_id,
    )


@router.get("/{function_id}/executions", response_model=PaginatedResponse[ExecutionRead])
async def list_executions(
    function_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> PaginatedResponse[ExecutionRead]:
    return await provider.list_executions(context, function_id, skip=skip, limit=limit)


@router.get("/status", response_model=FacadeStatusResponse)
async def functions_status(
    context=Depends(get_access_context),
    facade: FunctionsFacade = Depends(get_functions_facade),
) -> FacadeStatusResponse:
    return await facade.status(context)
