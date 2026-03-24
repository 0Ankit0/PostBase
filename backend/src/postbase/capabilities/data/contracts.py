from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class DataMutationPayload(BaseModel):
    values: dict[str, Any]


class DataQueryResult(BaseModel):
    rows: list[dict[str, Any]]


class DataProvider(Protocol):
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
