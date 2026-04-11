from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.apps.core.schemas import PaginatedResponse
from src.postbase.platform.contracts import ProviderAdapter


class DataMutationPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class DataQueryRequest(BaseModel):
    namespace: str
    table: str
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 100
    offset: int = 0
    order_by: str | None = None
    order_direction: str = "asc"


class DataQueryResult(BaseModel):
    rows: list[dict[str, Any]]


class DataMutationResult(BaseModel):
    success: bool
    row_id: int | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class DataProvider(ProviderAdapter, Protocol):
    async def query_rows(self, context, payload: DataQueryRequest) -> DataQueryResult:
        ...

    async def list_rows(
        self,
        context,
        namespace: str,
        table: str,
        *,
        skip: int,
        limit: int,
    ) -> PaginatedResponse[dict[str, Any]]:
        ...

    async def create_row(
        self,
        context,
        namespace: str,
        table: str,
        payload: DataMutationPayload,
    ) -> DataMutationResult:
        ...

    async def update_row(
        self,
        context,
        namespace: str,
        table: str,
        row_id: int,
        payload: DataMutationPayload,
    ) -> DataMutationResult:
        ...

    async def delete_row(self, context, namespace: str, table: str, row_id: int) -> None:
        ...
