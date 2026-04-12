from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import PostBaseContractModel
from src.postbase.platform.contracts import ProviderAdapter

CanonicalFilterOperator = Literal[
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "nin",
    "contains",
    "icontains",
    "is_null",
]


class DataMutationPayload(PostBaseContractModel):
    values: dict[str, Any] = Field(default_factory=dict)


class DataFilterClause(PostBaseContractModel):
    field: str
    op: CanonicalFilterOperator = "eq"
    value: Any | None = None


class DataSortClause(PostBaseContractModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class DataPagination(PostBaseContractModel):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class DataQueryRequest(PostBaseContractModel):
    namespace: str
    table: str
    filters: list[DataFilterClause] = Field(default_factory=list)
    pagination: DataPagination = Field(default_factory=DataPagination)
    sort: list[DataSortClause] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)

        raw_filters = payload.get("filters", [])
        if isinstance(raw_filters, dict):
            payload["filters"] = [
                {"field": field_name, "op": "eq", "value": field_value}
                for field_name, field_value in raw_filters.items()
            ]

        if "pagination" not in payload:
            payload["pagination"] = {
                "limit": payload.pop("limit", 100),
                "offset": payload.pop("offset", 0),
            }

        if "sort" not in payload:
            order_by = payload.pop("order_by", None)
            order_direction = payload.pop("order_direction", "asc")
            payload["sort"] = [{"field": order_by, "direction": order_direction}] if order_by else []

        return payload


class DataQueryResult(PostBaseContractModel):
    rows: list[dict[str, Any]]


class DataMutationResult(PostBaseContractModel):
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
