from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.data.contracts import DataMutationPayload, DataMutationResult, DataQueryRequest, DataQueryResult
from src.postbase.domain.enums import CapabilityKey, PolicyMode
from src.postbase.providers.data.adapter_translation import CanonicalDataQueryTranslator
from src.postbase.providers.data.postgres_advanced import build_postgres_table_plan
from src.postbase.domain.models import DataNamespace, TableDefinition
from src.postbase.platform.access import PostBaseAccessContext, validate_identifier
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage

class PostgresNativeDataProvider:
    def _ensure_postgres(self, db: AsyncSession) -> None:
        dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
        current = getattr(dialect_name, "name", None)
        if current != "postgresql":
            raise RuntimeError("PostgresNativeDataProvider requires a PostgreSQL database")

    def __init__(self) -> None:
        self._translator = CanonicalDataQueryTranslator()

    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.DATA,
            provider_key="postgres-native",
            supported_operations=["list", "query", "create", "update", "delete", "migrations"],
            optional_features=[
                "owner_policy",
                "extensions",
                "indexes",
                "partitioning",
                "sharding",
                "replication",
                "listen_notify",
                "jsonb",
                "citext",
                "vector",
            ],
            validation_checks=["postgres_required", "normalized_table_plan"],
            limits={"max_partition_count": 64, "max_listen_notify_channels_per_table": 8},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth()

    async def query_rows(self, context: PostBaseAccessContext, payload: DataQueryRequest) -> DataQueryResult:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, payload.namespace, payload.table)
        translated = self._translator.translate(
            filters=payload.filters,
            sort=payload.sort,
            pagination=payload.pagination,
        )

        sql = f"SELECT * FROM {self._qualified_table(db, namespace_row.physical_schema, table_row.table_name)}"
        params: dict[str, Any] = {}
        sql = self._apply_policy_read(context, table_row, sql, params)

        if translated.where_sql:
            sql += translated.where_sql.replace(" WHERE ", " AND ", 1) if " WHERE " in sql else translated.where_sql
        sql += translated.order_sql
        sql += " LIMIT :limit OFFSET :offset"
        params.update(translated.params)
        params["limit"] = translated.pagination.limit
        params["offset"] = translated.pagination.offset

        result = await db.execute(text(sql), params)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.DATA.value,
            metric_key="query_rows",
        )
        return DataQueryResult(rows=[dict(row) for row in result.mappings().all()])

    async def list_rows(
        self,
        context: PostBaseAccessContext,
        namespace: str,
        table: str,
        *,
        skip: int,
        limit: int,
    ) -> PaginatedResponse[dict[str, Any]]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, namespace, table)
        bounded_limit = min(max(limit, 1), 500)
        bounded_skip = max(skip, 0)
        from_sql = f"FROM {self._qualified_table(db, namespace_row.physical_schema, table_row.table_name)}"
        sql = f"SELECT * {from_sql}"
        params: dict[str, Any] = {}
        sql = self._apply_policy_read(context, table_row, sql, params)
        count_sql = self._apply_policy_read(context, table_row, f"SELECT COUNT(*) {from_sql}", dict(params))
        total = int((await db.execute(text(count_sql), params)).scalar_one())
        sql += " LIMIT :limit OFFSET :offset"
        params["limit"] = bounded_limit
        params["offset"] = bounded_skip
        result = await db.execute(text(sql), params)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.DATA.value,
            metric_key="list_rows",
        )
        return PaginatedResponse[dict[str, Any]].create(
            items=[dict(row) for row in result.mappings().all()],
            total=total,
            skip=bounded_skip,
            limit=bounded_limit,
        )

    async def create_row(
        self,
        context: PostBaseAccessContext,
        namespace: str,
        table: str,
        payload: DataMutationPayload,
    ) -> DataMutationResult:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, namespace, table)
        values = self._coerce_mutation_values(table_row, dict(payload.values))
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
        return DataMutationResult(success=True, values=values)

    async def update_row(
        self,
        context: PostBaseAccessContext,
        namespace: str,
        table: str,
        row_id: int,
        payload: DataMutationPayload,
    ) -> DataMutationResult:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        namespace_row, table_row = await self._resolve_table(db, context, namespace, table)
        values = self._coerce_mutation_values(table_row, dict(payload.values))
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
        return DataMutationResult(success=True, row_id=row_id, values=values)

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
        self._ensure_postgres(db)
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{namespace_row.physical_schema}"'))

    async def create_table(self, db: AsyncSession, namespace_row: DataNamespace, definition: TableDefinition) -> None:
        self._ensure_postgres(db)
        await self.create_namespace(db, namespace_row)
        table_plan = build_postgres_table_plan(
            schema=namespace_row.physical_schema,
            table_name=definition.table_name,
            columns=definition.columns_json,
            advanced_features=definition.advanced_features_json,
        )
        for statement in table_plan.statements:
            await db.execute(text(statement))

    async def table_exists(self, db: AsyncSession, namespace_row: DataNamespace, table_name: str) -> bool:
        self._ensure_postgres(db)
        result = await db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                """
            ),
            {"schema_name": namespace_row.physical_schema, "table_name": table_name},
        )
        return result.first() is not None

    async def list_table_columns(self, db: AsyncSession, namespace_row: DataNamespace, table_name: str) -> set[str]:
        self._ensure_postgres(db)
        result = await db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                """
            ),
            {"schema_name": namespace_row.physical_schema, "table_name": table_name},
        )
        return {str(row[0]) for row in result.fetchall()}

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
        self._ensure_postgres(db)
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

    def _coerce_mutation_values(self, table_row: TableDefinition, values: dict[str, Any]) -> dict[str, Any]:
        type_by_column = {
            str(column["name"]): str(column.get("type", "")).strip().lower()
            for column in table_row.columns_json
        }
        coerced: dict[str, Any] = {}
        for key, value in values.items():
            column_type = type_by_column.get(key)
            if column_type is None or value is None:
                coerced[key] = value
                continue
            if column_type == "datetime" and isinstance(value, str):
                coerced[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                continue
            if column_type == "date" and isinstance(value, str):
                coerced[key] = date.fromisoformat(value)
                continue
            if column_type == "time" and isinstance(value, str):
                coerced[key] = time.fromisoformat(value)
                continue
            if column_type == "uuid" and isinstance(value, str):
                coerced[key] = UUID(value)
                continue
            coerced[key] = value
        return coerced
