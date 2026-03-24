from __future__ import annotations

from fastapi import APIRouter, Depends

from src.postbase.capabilities.data.contracts import DataMutationPayload, DataQueryResult
from src.postbase.capabilities.data.dependencies import get_access_context, get_data_provider

router = APIRouter(prefix="/data", tags=["postbase-data"])


@router.get("/{namespace}/{table}", response_model=DataQueryResult)
async def list_rows(
    namespace: str,
    table: str,
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> DataQueryResult:
    return await provider.list_rows(context, namespace, table)


@router.post("/{namespace}/{table}")
async def create_row(
    namespace: str,
    table: str,
    payload: DataMutationPayload,
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> dict:
    return await provider.create_row(context, namespace, table, payload)


@router.patch("/{namespace}/{table}/{row_id}")
async def update_row(
    namespace: str,
    table: str,
    row_id: int,
    payload: DataMutationPayload,
    context=Depends(get_access_context),
    provider=Depends(get_data_provider),
) -> dict:
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
