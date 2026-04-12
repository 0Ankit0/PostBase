from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

from src.postbase.capabilities.data.contracts import DataFilterClause, DataPagination, DataSortClause
from src.postbase.platform.access import validate_identifier


@dataclass
class TranslatedDataQuery:
    where_sql: str = ""
    order_sql: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    pagination: DataPagination = field(default_factory=DataPagination)


class CanonicalDataQueryTranslator:
    def translate(
        self,
        *,
        filters: list[DataFilterClause],
        sort: list[DataSortClause],
        pagination: DataPagination,
    ) -> TranslatedDataQuery:
        where_parts: list[str] = []
        params: dict[str, Any] = {}

        for idx, clause in enumerate(filters):
            safe_field = validate_identifier(clause.field, "Filter field")
            field_sql = f'"{safe_field}"'
            param_name = f"filter_{idx}"
            list_param_name = f"{param_name}_list"

            if clause.op == "eq":
                where_parts.append(f"{field_sql} = :{param_name}")
                params[param_name] = clause.value
            elif clause.op == "neq":
                where_parts.append(f"{field_sql} != :{param_name}")
                params[param_name] = clause.value
            elif clause.op == "gt":
                where_parts.append(f"{field_sql} > :{param_name}")
                params[param_name] = clause.value
            elif clause.op == "gte":
                where_parts.append(f"{field_sql} >= :{param_name}")
                params[param_name] = clause.value
            elif clause.op == "lt":
                where_parts.append(f"{field_sql} < :{param_name}")
                params[param_name] = clause.value
            elif clause.op == "lte":
                where_parts.append(f"{field_sql} <= :{param_name}")
                params[param_name] = clause.value
            elif clause.op == "contains":
                where_parts.append(f"{field_sql} LIKE :{param_name}")
                params[param_name] = f"%{clause.value}%"
            elif clause.op == "icontains":
                where_parts.append(f"LOWER({field_sql}) LIKE LOWER(:{param_name})")
                params[param_name] = f"%{clause.value}%"
            elif clause.op == "is_null":
                where_parts.append(f"{field_sql} IS NULL" if clause.value else f"{field_sql} IS NOT NULL")
            elif clause.op in {"in", "nin"}:
                if not isinstance(clause.value, list):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Filter operator '{clause.op}' requires array value",
                    )
                if not clause.value:
                    where_parts.append("1 = 0" if clause.op == "in" else "1 = 1")
                else:
                    placeholders: list[str] = []
                    for value_idx, item in enumerate(clause.value):
                        item_param = f"{list_param_name}_{value_idx}"
                        placeholders.append(f":{item_param}")
                        params[item_param] = item
                    in_sql = f"{field_sql} IN ({', '.join(placeholders)})"
                    where_parts.append(f"NOT ({in_sql})" if clause.op == "nin" else in_sql)

        order_sql = ""
        if sort:
            order_parts: list[str] = []
            for item in sort:
                safe_column = validate_identifier(item.field, "Sort field")
                order_parts.append(f'"{safe_column}" {item.direction.upper()}')
            order_sql = " ORDER BY " + ", ".join(order_parts)

        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        return TranslatedDataQuery(where_sql=where_sql, order_sql=order_sql, params=params, pagination=pagination)
