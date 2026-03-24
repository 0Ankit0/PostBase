from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class DataMutationPayload(BaseModel):
    values: dict[str, Any]


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


class DataProvider(Protocol):
    async def query_rows(self, context, payload: DataQueryRequest) -> DataQueryResult:
        ...

    async def list_rows(self, context, namespace: str, table: str) -> DataQueryResult:
        ...

    async def create_row(self, context, namespace: str, table: str, payload: DataMutationPayload) -> dict[str, Any]:
        ...

    async def update_row(
        self,
        context,
        namespace: str,
        table: str,
        row_id: int,
        payload: DataMutationPayload,
    ) -> dict[str, Any]:
        ...

    async def delete_row(self, context, namespace: str, table: str, row_id: int) -> None:
        ...
