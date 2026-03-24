from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.capabilities.data.contracts import DataMutationPayload, DataQueryRequest, DataQueryResult
from src.postbase.domain.enums import CapabilityKey, PolicyMode
from src.postbase.domain.models import DataNamespace, TableDefinition
from src.postbase.platform.access import PostBaseAccessContext, validate_identifier
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


TYPE_MAP = {
    "string": "VARCHAR(255)",
    "text": "TEXT",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "float": "FLOAT",
    "datetime": "TIMESTAMP",
    "json": "TEXT",
}


class PostgresNativeDataProvider:
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.DATA,
            provider_key="postgres-native",
            supported_operations=["list", "query", "create", "update", "delete"],
            optional_features=["owner_policy"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth()

    async def query_rows(self, context: PostBaseAccessContext, payload: DataQueryRequest) -> DataQueryResult:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, payload.namespace, payload.table)
        limit = min(max(payload.limit, 1), 500)
        offset = max(payload.offset, 0)

        sql = f"SELECT * FROM {self._qualified_table(db, namespace_row.physical_schema, table_row.table_name)}"
        params: dict[str, Any] = {}
        sql = self._apply_policy_read(context, table_row, sql, params)

        has_where = " WHERE " in sql
        for idx, (column_name, column_value) in enumerate(payload.filters.items()):
            safe_column_name = validate_identifier(column_name, "Column")
            param_name = f"filter_{idx}"
            sql += f' {"AND" if has_where else "WHERE"} "{safe_column_name}" = :{param_name}'
            params[param_name] = column_value
            has_where = True

        if payload.order_by:
            safe_order_column = validate_identifier(payload.order_by, "Order by column")
            direction = payload.order_direction.lower()
            if direction not in {"asc", "desc"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="order_direction must be 'asc' or 'desc'",
                )
            sql += f' ORDER BY "{safe_order_column}" {direction.upper()}'

        sql += " LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = await db.execute(text(sql), params)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.DATA.value,
            metric_key="query_rows",
        )
        return DataQueryResult(rows=[dict(row) for row in result.mappings().all()])

    async def list_rows(self, context: PostBaseAccessContext, namespace: str, table: str) -> DataQueryResult:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, namespace, table)
        sql = f"SELECT * FROM {self._qualified_table(db, namespace_row.physical_schema, table_row.table_name)}"
        params: dict[str, Any] = {}
        sql = self._apply_policy_read(context, table_row, sql, params)
        result = await db.execute(text(sql), params)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.DATA.value,
            metric_key="list_rows",
        )
        return DataQueryResult(rows=[dict(row) for row in result.mappings().all()])

    async def create_row(
        self,
        context: PostBaseAccessContext,
        namespace: str,
        table: str,
        payload: DataMutationPayload,
    ) -> dict[str, Any]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, namespace, table)
        values = dict(payload.values)
        self._enforce_write_policy(context, table_row, values)
        columns = ", ".join(f'"{key}"' for key in values.keys())
        placeholders = ", ".join(f":{key}" for key in values.keys())
        sql = (
            f"INSERT INTO {self._qualified_table(db, namespace_row.physical_schema, table_row.table_name)} "
            f"({columns}) VALUES ({placeholders})"
        )
        await db.execute(text(sql), values)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.DATA.value,
            metric_key="create_row",
        )
        await db.commit()
        return {"created": True, "values": values}

    async def update_row(
        self,
        context: PostBaseAccessContext,
        namespace: str,
        table: str,
        row_id: int,
        payload: DataMutationPayload,
    ) -> dict[str, Any]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, namespace, table)
        values = dict(payload.values)
        assignments = ", ".join(f'"{key}" = :{key}' for key in values.keys())
        params: dict[str, Any] = {**values, "row_id": row_id}
        sql = (
            f"UPDATE {self._qualified_table(db, namespace_row.physical_schema, table_row.table_name)} "
            f"SET {assignments} WHERE id = :row_id"
        )
        sql = self._apply_policy_write(context, table_row, sql, params)
        await db.execute(text(sql), params)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.DATA.value,
            metric_key="update_row",
        )
        await db.commit()
        return {"updated": True, "row_id": row_id}

    async def delete_row(self, context: PostBaseAccessContext, namespace: str, table: str, row_id: int) -> None:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, namespace, table)
        params: dict[str, Any] = {"row_id": row_id}
        sql = (
            f"DELETE FROM {self._qualified_table(db, namespace_row.physical_schema, table_row.table_name)} "
            f"WHERE id = :row_id"
        )
        sql = self._apply_policy_write(context, table_row, sql, params)
        await db.execute(text(sql), params)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.DATA.value,
            metric_key="delete_row",
        )
        await db.commit()

    async def create_namespace(self, db: AsyncSession, namespace_row: DataNamespace) -> None:
        if db.bind.dialect.name != "sqlite":
            await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{namespace_row.physical_schema}"'))

    async def create_table(self, db: AsyncSession, namespace_row: DataNamespace, definition: TableDefinition) -> None:
        if db.bind.dialect.name == "sqlite":
            column_defs = ['"id" INTEGER PRIMARY KEY AUTOINCREMENT']
        else:
            column_defs = ['"id" BIGSERIAL PRIMARY KEY']
        for column in definition.columns_json:
            if column["name"] == "id":
                continue
            sql_type = TYPE_MAP.get(column["type"], "TEXT")
            nullable = "" if column.get("nullable", True) else " NOT NULL"
            if column.get("primary_key", False):
                nullable = " PRIMARY KEY"
            column_defs.append(f'"{column["name"]}" {sql_type}{nullable}')
        sql = (
            f"CREATE TABLE IF NOT EXISTS {self._qualified_table(db, namespace_row.physical_schema, definition.table_name)} "
            f"({', '.join(column_defs)})"
        )
        await db.execute(text(sql))

    async def _resolve_table(
        self,
        db: AsyncSession,
        context: PostBaseAccessContext,
        namespace: str,
        table: str,
    ) -> tuple[DataNamespace, TableDefinition]:
        namespace_name = validate_identifier(namespace, "Namespace")
        table_name = validate_identifier(table, "Table")
        namespace_row = (
            await db.execute(
                select(DataNamespace).where(
                    DataNamespace.environment_id == context.environment_id,
                    DataNamespace.name == namespace_name,
                )
            )
        ).scalars().first()
        if namespace_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Namespace not found")
        table_row = (
            await db.execute(
                select(TableDefinition).where(
                    TableDefinition.namespace_id == namespace_row.id,
                    TableDefinition.table_name == table_name,
                )
            )
        ).scalars().first()
        if table_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
        return namespace_row, table_row

    def _qualified_table(self, db: AsyncSession, schema: str, table: str) -> str:
        if db.bind.dialect.name == "sqlite":
            return f'"{schema}__{table}"'
        return f'"{schema}"."{table}"'

    def _apply_policy_read(
        self,
        context: PostBaseAccessContext,
        table_row: TableDefinition,
        sql: str,
        params: dict[str, Any],
    ) -> str:
        self._ensure_policy_access(context, table_row)
        if table_row.policy_mode == PolicyMode.OWNER and not context.service_role:
            if not table_row.owner_column or context.auth_user_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner policy misconfigured")
            params["auth_user_id"] = context.auth_user_id
            sql += f' WHERE "{table_row.owner_column}" = :auth_user_id'
        return sql

    def _apply_policy_write(
        self,
        context: PostBaseAccessContext,
        table_row: TableDefinition,
        sql: str,
        params: dict[str, Any],
    ) -> str:
        self._ensure_policy_access(context, table_row)
        if table_row.policy_mode == PolicyMode.OWNER and not context.service_role:
            if not table_row.owner_column or context.auth_user_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner policy misconfigured")
            params["auth_user_id"] = context.auth_user_id
            sql += f' AND "{table_row.owner_column}" = :auth_user_id'
        return sql

    def _ensure_policy_access(self, context: PostBaseAccessContext, table_row: TableDefinition) -> None:
        if table_row.policy_mode == PolicyMode.PUBLIC:
            return
        if table_row.policy_mode == PolicyMode.SERVICE and not context.service_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service role required")
        if table_row.policy_mode in {PolicyMode.AUTHENTICATED, PolicyMode.OWNER} and not context.authenticated:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authenticated access required")

    def _enforce_write_policy(
        self,
        context: PostBaseAccessContext,
        table_row: TableDefinition,
        values: dict[str, Any],
    ) -> None:
        self._ensure_policy_access(context, table_row)
        if table_row.policy_mode == PolicyMode.OWNER and not context.service_role:
            if not table_row.owner_column or context.auth_user_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner policy misconfigured")
            values[table_row.owner_column] = context.auth_user_id
