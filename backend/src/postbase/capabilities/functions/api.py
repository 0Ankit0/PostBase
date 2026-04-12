from fastapi import APIRouter, Depends, Header, Query

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import CAPABILITY_ERROR_RESPONSES, FacadeStatusResponse
from src.postbase.capabilities.functions.contracts import (
    FunctionDeploymentEventRead,
    FunctionDeploymentRevisionRead,
    ExecutionRead,
    FunctionCreateRequest,
    FunctionInvokeRequest,
    FunctionRead,
    FunctionScheduleCreateRequest,
    FunctionScheduleRead,
)
from src.postbase.capabilities.functions.dependencies import get_access_context, get_functions_facade, get_functions_provider
from src.postbase.capabilities.functions.service import FunctionsFacade

router = APIRouter(prefix="/functions", tags=["postbase-functions"])


@router.post("", response_model=FunctionRead, responses=CAPABILITY_ERROR_RESPONSES)
async def create_function(
    payload: FunctionCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> FunctionRead:
    return await provider.create_function(context, payload)


@router.get("", response_model=PaginatedResponse[FunctionRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_functions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> PaginatedResponse[FunctionRead]:
    return await provider.list_functions(context, skip=skip, limit=limit)


@router.post("/{function_id}/invoke", response_model=ExecutionRead, responses=CAPABILITY_ERROR_RESPONSES)
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


@router.get("/{function_id}/executions", response_model=PaginatedResponse[ExecutionRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_executions(
    function_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> PaginatedResponse[ExecutionRead]:
    return await provider.list_executions(context, function_id, skip=skip, limit=limit)


@router.post("/{function_id}/schedules", response_model=FunctionScheduleRead, responses=CAPABILITY_ERROR_RESPONSES)
async def create_schedule(
    function_id: int,
    payload: FunctionScheduleCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> FunctionScheduleRead:
    return await provider.create_schedule(context, function_id, payload)


@router.get("/{function_id}/schedules", response_model=PaginatedResponse[FunctionScheduleRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_schedules(
    function_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> PaginatedResponse[FunctionScheduleRead]:
    return await provider.list_schedules(context, function_id, skip=skip, limit=limit)


@router.post("/{function_id}/schedules/{schedule_id}/pause", response_model=FunctionScheduleRead, responses=CAPABILITY_ERROR_RESPONSES)
async def pause_schedule(
    function_id: int,
    schedule_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> FunctionScheduleRead:
    return await provider.pause_schedule(context, function_id, schedule_id)


@router.post("/{function_id}/schedules/{schedule_id}/resume", response_model=FunctionScheduleRead, responses=CAPABILITY_ERROR_RESPONSES)
async def resume_schedule(
    function_id: int,
    schedule_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> FunctionScheduleRead:
    return await provider.resume_schedule(context, function_id, schedule_id)


@router.post("/{function_id}/schedules/{schedule_id}/run-now", response_model=ExecutionRead, responses=CAPABILITY_ERROR_RESPONSES)
async def run_schedule_now(
    function_id: int,
    schedule_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> ExecutionRead:
    return await provider.run_schedule_now(context, function_id, schedule_id)


@router.delete("/{function_id}/schedules/{schedule_id}", status_code=204, responses=CAPABILITY_ERROR_RESPONSES)
async def delete_schedule(
    function_id: int,
    schedule_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> None:
    await provider.delete_schedule(context, function_id, schedule_id)


@router.get("/{function_id}/deployments", response_model=PaginatedResponse[FunctionDeploymentEventRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_deployments(
    function_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> PaginatedResponse[FunctionDeploymentEventRead]:
    return await provider.list_deployment_history(context, function_id, skip=skip, limit=limit)


@router.get("/{function_id}/revisions", response_model=PaginatedResponse[FunctionDeploymentRevisionRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_revisions(
    function_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> PaginatedResponse[FunctionDeploymentRevisionRead]:
    return await provider.list_revisions(context, function_id, skip=skip, limit=limit)


@router.post("/{function_id}/revisions/{revision_id}/rollback", response_model=FunctionRead, responses=CAPABILITY_ERROR_RESPONSES)
async def rollback_revision(
    function_id: int,
    revision_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_functions_provider),
) -> FunctionRead:
    return await provider.rollback_revision(context, function_id, revision_id)


@router.get("/status", response_model=FacadeStatusResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def functions_status(
    context=Depends(get_access_context),
    facade: FunctionsFacade = Depends(get_functions_facade),
) -> FacadeStatusResponse:
    return await facade.status(context)
