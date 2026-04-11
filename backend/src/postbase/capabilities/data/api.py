from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import FacadeStatusResponse
from src.postbase.capabilities.data.contracts import DataMutationPayload, DataMutationResult, DataQueryRequest, DataQueryResult
from src.postbase.capabilities.data.dependencies import get_access_context, get_data_facade, get_data_provider
from src.postbase.capabilities.data.service import DataFacade

router = APIRouter(prefix="/data", tags=["postbase-data"])


@router.post("/query", response_model=DataQueryResult)
async def query_rows(
    payload: DataQueryRequest,
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> DataQueryResult:
    return await provider.query_rows(context, payload)


@router.get("/{namespace}/{table}", response_model=PaginatedResponse[dict[str, Any]])
async def list_rows(
    namespace: str,
    table: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> PaginatedResponse[dict[str, Any]]:
    return await provider.list_rows(context, namespace, table, skip=skip, limit=limit)


@router.post("/{namespace}/{table}", response_model=DataMutationResult)
async def create_row(
    namespace: str,
    table: str,
    payload: DataMutationPayload,
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> DataMutationResult:
    return await provider.create_row(context, namespace, table, payload)


@router.patch("/{namespace}/{table}/{row_id}", response_model=DataMutationResult)
async def update_row(
    namespace: str,
    table: str,
    row_id: int,
    payload: DataMutationPayload,
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> DataMutationResult:
    return await provider.update_row(context, namespace, table, row_id, payload)


@router.delete("/{namespace}/{table}/{row_id}", status_code=204)
async def delete_row(
    namespace: str,
    table: str,
    row_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> None:
    await provider.delete_row(context, namespace, table, row_id)


@router.get("/status", response_model=FacadeStatusResponse)
async def data_status(
    context=Depends(get_access_context),
    facade: DataFacade = Depends(get_data_facade),
) -> FacadeStatusResponse:
    return await facade.status(context)
