from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import re
from typing import Any

from fastapi import HTTPException, status

from src.postbase.platform.access import validate_identifier

TYPE_MAP = {
    "string": "VARCHAR(255)",
    "text": "TEXT",
    "integer": "INTEGER",
    "bigint": "BIGINT",
    "boolean": "BOOLEAN",
    "float": "DOUBLE PRECISION",
    "numeric": "NUMERIC(12,2)",
    "date": "DATE",
    "time": "TIME",
    "datetime": "TIMESTAMP",
    "json": "JSONB",
    "jsonb": "JSONB",
    "uuid": "UUID",
    "citext": "CITEXT",
}

TYPE_EXTENSION_MAP = {
    "citext": "citext",
}

SUPPORTED_EXTENSIONS = {
    "btree_gin": "btree_gin",
    "btree_gist": "btree_gist",
    "citext": "citext",
    "hstore": "hstore",
    "pg_trgm": "pg_trgm",
    "pgcrypto": "pgcrypto",
    "pgvector": "vector",
    "uuid-ossp": "uuid-ossp",
    "vector": "vector",
}
SUPPORTED_INDEX_METHODS = {"btree", "brin", "gin", "gist", "hash"}
SUPPORTED_PARTITION_STRATEGIES = {"hash", "list", "range"}
SUPPORTED_NOTIFY_EVENTS = {"delete", "insert", "update"}
SUPPORTED_REPLICATION_MODES = {"logical", "physical", "hybrid"}
SUPPORTED_REPLICA_IDENTITIES = {"default", "full", "nothing", "using_index"}
SUPPORTED_SHARDING_STRATEGIES = {"logical", "native_hash_partitioning"}
SAFE_SQL_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\(\d+(,\d+)?\))?$")


@dataclass(slots=True)
class PostgresTablePlan:
    normalized_columns: list[dict[str, Any]]
    normalized_advanced_features: dict[str, Any]
    statements: list[str]
    applied_sql: str


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _quote_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return f"'{str(value).replace(chr(39), chr(39) * 2)}'"


def _qualified_table(schema: str, table_name: str) -> str:
    return f'{_quote_identifier(schema)}.{_quote_identifier(table_name)}'


def _build_runtime_identifier(prefix: str, *parts: str) -> str:
    normalized = "_".join(
        re.sub(r"[^a-z0-9_]+", "_", part.lower()).strip("_")
        for part in (prefix, *parts)
        if part
    )
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = prefix
    if len(normalized) <= 63:
        return normalized
    digest = sha1(normalized.encode("utf-8")).hexdigest()[:10]
    head = normalized[: 63 - len(digest) - 1].rstrip("_")
    return f"{head}_{digest}"


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in items:
        if item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


def _normalize_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _normalize_int(value: Any, *, field_name: str, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise _invalid(f"{field_name} must be an integer") from exc
    if parsed < minimum:
        raise _invalid(f"{field_name} must be greater than or equal to {minimum}")
    return parsed


def _ensure_known_columns(columns: set[str], candidates: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    for candidate in candidates:
        normalized_name = validate_identifier(candidate, field_name)
        if normalized_name not in columns:
            raise _invalid(f"{field_name} '{normalized_name}' is not defined on the table")
        normalized.append(normalized_name)
    return _dedupe_preserve_order(normalized)


def _resolve_sql_type(column_type: str) -> tuple[str, str | None]:
    normalized = column_type.strip().lower()
    mapped = TYPE_MAP.get(normalized)
    if mapped is not None:
        return mapped, TYPE_EXTENSION_MAP.get(normalized)
    if SAFE_SQL_TYPE_RE.fullmatch(normalized):
        extension = "vector" if normalized.startswith("vector(") else None
        return normalized.upper(), extension
    raise _invalid(f"Unsupported column type '{column_type}'")


def normalize_table_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_column in columns:
        column_name = validate_identifier(str(raw_column.get("name", "")), "Column name")
        if column_name in seen:
            raise _invalid(f"Column '{column_name}' is defined more than once")
        sql_type, required_extension = _resolve_sql_type(str(raw_column.get("type", "text")))
        normalized_column = {
            "name": column_name,
            "type": str(raw_column.get("type", "text")).strip().lower(),
            "nullable": _normalize_bool(raw_column.get("nullable"), default=True),
            "primary_key": _normalize_bool(raw_column.get("primary_key"), default=False),
            "sql_type": sql_type,
        }
        if required_extension is not None:
            normalized_column["required_extension"] = required_extension
        normalized_columns.append(normalized_column)
        seen.add(column_name)
    return normalized_columns


def _normalize_extensions(
    extensions: list[Any],
    *,
    normalized_columns: list[dict[str, Any]],
) -> list[str]:
    requested = [str(item).strip().lower() for item in extensions]
    requested.extend(
        column["required_extension"]
        for column in normalized_columns
        if column.get("required_extension") is not None
    )
    normalized: list[str] = []
    for extension in requested:
        resolved = SUPPORTED_EXTENSIONS.get(extension)
        if resolved is None:
            raise _invalid(f"Unsupported PostgreSQL extension '{extension}'")
        normalized.append(resolved)
    return _dedupe_preserve_order(normalized)


def _normalize_indexes(
    indexes: list[dict[str, Any]],
    *,
    known_columns: set[str],
    table_name: str,
) -> list[dict[str, Any]]:
    normalized_indexes: list[dict[str, Any]] = []
    for raw_index in indexes:
        index_columns = _ensure_known_columns(
            known_columns,
            list(raw_index.get("columns", [])),
            field_name="Index column",
        )
        if not index_columns:
            raise _invalid("Each index must include at least one column")
        include_columns = _ensure_known_columns(
            known_columns,
            list(raw_index.get("include_columns", [])),
            field_name="Index include column",
        )
        method = str(raw_index.get("method", "btree")).strip().lower()
        if method not in SUPPORTED_INDEX_METHODS:
            raise _invalid(f"Unsupported PostgreSQL index method '{method}'")
        requested_name = raw_index.get("name")
        index_name = (
            validate_identifier(str(requested_name), "Index name")
            if requested_name
            else _build_runtime_identifier("ix", table_name, *index_columns)
        )
        normalized_indexes.append(
            {
                "name": index_name,
                "columns": index_columns,
                "unique": _normalize_bool(raw_index.get("unique"), default=False),
                "method": method,
                "include_columns": include_columns,
            }
        )
    return normalized_indexes


def _normalize_partitioning(
    partitioning: dict[str, Any] | None,
    *,
    known_columns: set[str],
    table_name: str,
) -> dict[str, Any] | None:
    if not partitioning:
        return None
    strategy = str(partitioning.get("strategy", "")).strip().lower()
    if strategy not in SUPPORTED_PARTITION_STRATEGIES:
        raise _invalid(f"Unsupported PostgreSQL partitioning strategy '{strategy}'")
    partition_columns = _ensure_known_columns(
        known_columns,
        list(partitioning.get("columns", [])),
        field_name="Partition column",
    )
    if not partition_columns:
        raise _invalid("Partitioning requires at least one partition column")

    normalized: dict[str, Any] = {
        "strategy": strategy,
        "columns": partition_columns,
    }
    raw_partitions = list(partitioning.get("partitions", []))
    if strategy == "hash":
        partition_count = _normalize_int(partitioning.get("partition_count", len(raw_partitions) or 4), field_name="partition_count")
        normalized["partition_count"] = partition_count
        normalized["partitions"] = [
            {
                "name": _build_runtime_identifier(table_name, "p", "hash", str(remainder)),
                "modulus": partition_count,
                "remainder": remainder,
            }
            for remainder in range(partition_count)
        ]
        return normalized

    if not raw_partitions:
        raise _invalid(f"{strategy} partitioning requires explicit partitions")

    normalized_partitions: list[dict[str, Any]] = []
    for index, raw_partition in enumerate(raw_partitions, start=1):
        partition_name = raw_partition.get("name")
        normalized_name = (
            validate_identifier(str(partition_name), "Partition name")
            if partition_name
            else _build_runtime_identifier(table_name, "p", strategy, str(index))
        )
        if strategy == "range":
            if raw_partition.get("from_value") is None or raw_partition.get("to_value") is None:
                raise _invalid("Range partitions require both from_value and to_value")
            normalized_partitions.append(
                {
                    "name": normalized_name,
                    "from_value": raw_partition.get("from_value"),
                    "to_value": raw_partition.get("to_value"),
                }
            )
        else:
            values = list(raw_partition.get("values", []))
            if not values:
                raise _invalid("List partitions require at least one value")
            normalized_partitions.append({"name": normalized_name, "values": values})
    normalized["partitions"] = normalized_partitions
    return normalized


def _normalize_sharding(
    sharding: dict[str, Any] | None,
    *,
    known_columns: set[str],
) -> dict[str, Any] | None:
    if not sharding:
        return None
    strategy = str(sharding.get("strategy", "logical")).strip().lower()
    if strategy not in SUPPORTED_SHARDING_STRATEGIES:
        raise _invalid(f"Unsupported sharding strategy '{strategy}'")
    shard_key = validate_identifier(str(sharding.get("shard_key", "")), "Shard key")
    if shard_key not in known_columns:
        raise _invalid(f"Shard key '{shard_key}' is not defined on the table")
    shard_count = _normalize_int(sharding.get("shard_count", 4), field_name="shard_count")
    return {
        "strategy": strategy,
        "shard_key": shard_key,
        "shard_count": shard_count,
        "routing_header": sharding.get("routing_header") or "X-PostBase-Shard-Key",
        "colocate_with": sharding.get("colocate_with"),
    }


def _normalize_replication(
    replication: dict[str, Any] | None,
    *,
    known_index_names: set[str],
) -> dict[str, Any] | None:
    if not replication:
        return None
    mode = str(replication.get("mode", "logical")).strip().lower()
    if mode not in SUPPORTED_REPLICATION_MODES:
        raise _invalid(f"Unsupported replication mode '{mode}'")
    publish_operations = [
        str(operation).strip().lower()
        for operation in replication.get("publish_operations", ["insert", "update", "delete"])
    ]
    if not publish_operations:
        raise _invalid("Replication publish_operations must include at least one operation")
    for operation in publish_operations:
        if operation not in {"insert", "update", "delete", "truncate"}:
            raise _invalid(f"Unsupported replication publish operation '{operation}'")
    replica_identity = str(replication.get("replica_identity", "default")).strip().lower()
    if replica_identity not in SUPPORTED_REPLICA_IDENTITIES:
        raise _invalid(f"Unsupported replica_identity '{replica_identity}'")
    replica_identity_index = replication.get("replica_identity_index")
    if replica_identity == "using_index":
        if not replica_identity_index:
            raise _invalid("replica_identity_index is required when replica_identity is 'using_index'")
        normalized_index = validate_identifier(str(replica_identity_index), "Replica identity index")
        if normalized_index not in known_index_names:
            raise _invalid(f"Replica identity index '{normalized_index}' is not defined on the table")
    else:
        normalized_index = None
    publication_name = replication.get("publication_name")
    return {
        "mode": mode,
        "managed": _normalize_bool(replication.get("managed"), default=False),
        "publication_name": validate_identifier(str(publication_name), "Publication name") if publication_name else None,
        "publish_operations": _dedupe_preserve_order(publish_operations),
        "replica_identity": replica_identity,
        "replica_identity_index": normalized_index,
        "read_replica_endpoints": [str(item) for item in replication.get("read_replica_endpoints", [])],
    }


def _normalize_listen_notify(
    listen_notify: list[dict[str, Any]],
    *,
    known_columns: set[str],
) -> list[dict[str, Any]]:
    normalized_notifications: list[dict[str, Any]] = []
    for raw_notification in listen_notify:
        channel = validate_identifier(str(raw_notification.get("channel", "")), "Listen/notify channel")
        events = [
            str(event).strip().lower()
            for event in raw_notification.get("events", ["insert", "update", "delete"])
        ]
        if not events:
            raise _invalid("listen_notify events must include at least one operation")
        for event in events:
            if event not in SUPPORTED_NOTIFY_EVENTS:
                raise _invalid(f"Unsupported listen_notify event '{event}'")
        payload_columns = _ensure_known_columns(
            known_columns,
            list(raw_notification.get("payload_columns", [])),
            field_name="Listen/notify payload column",
        )
        normalized_notifications.append(
            {
                "channel": channel,
                "events": _dedupe_preserve_order(events),
                "payload_columns": payload_columns,
            }
        )
    return normalized_notifications


def _merge_sharding_partitioning(
    *,
    sharding: dict[str, Any] | None,
    partitioning: dict[str, Any] | None,
    table_name: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if sharding is None or sharding["strategy"] != "native_hash_partitioning":
        return sharding, partitioning
    derived_partitioning = {
        "strategy": "hash",
        "columns": [sharding["shard_key"]],
        "partition_count": sharding["shard_count"],
        "partitions": [
            {
                "name": _build_runtime_identifier(table_name, "shard", str(remainder)),
                "modulus": sharding["shard_count"],
                "remainder": remainder,
            }
            for remainder in range(sharding["shard_count"])
        ],
        "managed_by_sharding": True,
    }
    if partitioning is None:
        return sharding, derived_partitioning
    if partitioning["strategy"] != "hash" or partitioning["columns"] != [sharding["shard_key"]]:
        raise _invalid(
            "native_hash_partitioning sharding requires hash partitioning on the shard key or no explicit partitioning"
        )
    if partitioning.get("partition_count") != sharding["shard_count"]:
        raise _invalid("native_hash_partitioning shard_count must match hash partition_count")
    partitioning["managed_by_sharding"] = True
    return sharding, partitioning


def normalize_postgres_advanced_features(
    *,
    table_name: str,
    normalized_columns: list[dict[str, Any]],
    advanced_features: dict[str, Any] | None,
) -> dict[str, Any]:
    feature_payload = advanced_features or {}
    known_columns = {"id", *(column["name"] for column in normalized_columns)}
    extensions = _normalize_extensions(list(feature_payload.get("extensions", [])), normalized_columns=normalized_columns)
    indexes = _normalize_indexes(list(feature_payload.get("indexes", [])), known_columns=known_columns, table_name=table_name)

    sharding = _normalize_sharding(feature_payload.get("sharding"), known_columns=known_columns)
    partitioning = _normalize_partitioning(
        feature_payload.get("partitioning"),
        known_columns=known_columns,
        table_name=table_name,
    )
    sharding, partitioning = _merge_sharding_partitioning(
        sharding=sharding,
        partitioning=partitioning,
        table_name=table_name,
    )

    auto_indexes = list(indexes)
    if partitioning is not None:
        auto_indexes.append(
            {
                "name": _build_runtime_identifier("ix", table_name, "id"),
                "columns": ["id"],
                "unique": False,
                "method": "btree",
                "include_columns": [],
                "managed": True,
            }
        )
    if sharding is not None and sharding["strategy"] == "logical":
        auto_indexes.append(
            {
                "name": _build_runtime_identifier("ix", table_name, sharding["shard_key"]),
                "columns": [sharding["shard_key"]],
                "unique": False,
                "method": "btree",
                "include_columns": [],
                "managed": True,
            }
        )
    normalized_indexes = _normalize_indexes(auto_indexes, known_columns=known_columns, table_name=table_name)
    index_names = {item["name"] for item in normalized_indexes}
    replication = _normalize_replication(feature_payload.get("replication"), known_index_names=index_names)
    listen_notify = _normalize_listen_notify(list(feature_payload.get("listen_notify", [])), known_columns=known_columns)

    if partitioning is not None and any(column["primary_key"] for column in normalized_columns):
        raise _invalid(
            "Partitioned tables are not compatible with custom primary_key column definitions in the current PostBase planner"
        )

    normalized_features: dict[str, Any] = {}
    if extensions:
        normalized_features["extensions"] = extensions
    if normalized_indexes:
        normalized_features["indexes"] = normalized_indexes
    if partitioning is not None:
        normalized_features["partitioning"] = partitioning
    if sharding is not None:
        normalized_features["sharding"] = sharding
    if replication is not None:
        normalized_features["replication"] = replication
    if listen_notify:
        normalized_features["listen_notify"] = listen_notify
    if normalized_features:
        normalized_features["integration_manifest"] = build_postgres_integration_manifest(
            table_name=table_name,
            advanced_features=normalized_features,
        )
    return normalized_features


def build_postgres_integration_manifest(*, table_name: str, advanced_features: dict[str, Any]) -> dict[str, Any]:
    partitioning = advanced_features.get("partitioning")
    sharding = advanced_features.get("sharding")
    replication = advanced_features.get("replication")
    listen_notify = advanced_features.get("listen_notify", [])
    return {
        "postgres_capabilities": sorted(
            [
                key
                for key in ("extensions", "indexes", "partitioning", "sharding", "replication", "listen_notify")
                if advanced_features.get(key)
            ]
        ),
        "notifications": [
            {
                "channel": item["channel"],
                "events": item["events"],
                "listen_command": f"LISTEN {item['channel']};",
            }
            for item in listen_notify
        ],
        "partitioning": {
            "strategy": partitioning["strategy"],
            "columns": partitioning["columns"],
            "partition_count": partitioning.get("partition_count", len(partitioning.get("partitions", []))),
        }
        if partitioning
        else None,
        "sharding": {
            "strategy": sharding["strategy"],
            "shard_key": sharding["shard_key"],
            "shard_count": sharding["shard_count"],
            "routing_header": sharding["routing_header"],
            "requires_external_router": sharding["strategy"] == "logical",
        }
        if sharding
        else None,
        "replication": {
            "mode": replication["mode"],
            "publication_name": replication["publication_name"],
            "managed": replication["managed"],
            "publish_operations": replication["publish_operations"],
            "read_replica_endpoints": replication["read_replica_endpoints"],
            "requires_external_setup": replication["mode"] in {"physical", "hybrid"}
            or bool(replication["read_replica_endpoints"])
            or bool(replication["publication_name"] and not replication["managed"]),
        }
        if replication
        else None,
        "application_integration": {
            "table": table_name,
            "recommended_client_patterns": [
                pattern
                for pattern, enabled in (
                    ("notification-consumer", bool(listen_notify)),
                    ("partition-aware-write-path", bool(partitioning)),
                    ("shard-routing-header", bool(sharding and sharding["strategy"] == "logical")),
                    ("replication-aware-read-routing", bool(replication)),
                )
                if enabled
            ]
        },
    }


def _build_partition_clause(partitioning: dict[str, Any] | None) -> str:
    if partitioning is None:
        return ""
    columns = ", ".join(_quote_identifier(column) for column in partitioning["columns"])
    return f" PARTITION BY {partitioning['strategy'].upper()} ({columns})"


def _build_column_definitions(
    *,
    normalized_columns: list[dict[str, Any]],
    partitioning: dict[str, Any] | None,
) -> list[str]:
    is_partitioned = partitioning is not None
    has_explicit_id = any(column["name"] == "id" for column in normalized_columns)
    column_definitions = []
    if not has_explicit_id:
        column_definitions.append('"id" BIGSERIAL NOT NULL' if is_partitioned else '"id" BIGSERIAL PRIMARY KEY')
    for column in normalized_columns:
        nullable = "" if column["nullable"] else " NOT NULL"
        if column["primary_key"]:
            nullable = " PRIMARY KEY"
        column_definitions.append(f'{_quote_identifier(column["name"])} {column["sql_type"]}{nullable}')
    return column_definitions


def _build_partition_statements(schema: str, table_name: str, partitioning: dict[str, Any] | None) -> list[str]:
    if partitioning is None:
        return []
    qualified_parent = _qualified_table(schema, table_name)
    statements: list[str] = []
    for partition in partitioning["partitions"]:
        qualified_partition = _qualified_table(schema, partition["name"])
        if partitioning["strategy"] == "range":
            clause = (
                f"FOR VALUES FROM ({_quote_literal(partition['from_value'])}) "
                f"TO ({_quote_literal(partition['to_value'])})"
            )
        elif partitioning["strategy"] == "list":
            values = ", ".join(_quote_literal(value) for value in partition["values"])
            clause = f"FOR VALUES IN ({values})"
        else:
            clause = f"FOR VALUES WITH (MODULUS {partition['modulus']}, REMAINDER {partition['remainder']})"
        statements.append(
            f"CREATE TABLE IF NOT EXISTS {qualified_partition} PARTITION OF {qualified_parent} {clause}"
        )
    return statements


def _build_index_statements(schema: str, table_name: str, indexes: list[dict[str, Any]]) -> list[str]:
    qualified_table = _qualified_table(schema, table_name)
    statements: list[str] = []
    for index in indexes:
        columns = ", ".join(_quote_identifier(column) for column in index["columns"])
        include_clause = ""
        if index["include_columns"]:
            include_columns = ", ".join(_quote_identifier(column) for column in index["include_columns"])
            include_clause = f" INCLUDE ({include_columns})"
        unique_clause = "UNIQUE " if index["unique"] else ""
        statements.append(
            " ".join(
                part
                for part in (
                    f"CREATE {unique_clause}INDEX IF NOT EXISTS {_quote_identifier(index['name'])}",
                    f"ON {qualified_table}",
                    f"USING {index['method'].upper()} ({columns})",
                    include_clause,
                )
                if part
            )
        )
    return statements


def _build_replication_statements(schema: str, table_name: str, replication: dict[str, Any] | None) -> list[str]:
    if replication is None:
        return []
    statements: list[str] = []
    qualified_table = _qualified_table(schema, table_name)
    replica_identity = replication["replica_identity"]
    if replica_identity == "using_index":
        statements.append(
            f"ALTER TABLE {qualified_table} REPLICA IDENTITY USING INDEX {_quote_identifier(replication['replica_identity_index'])}"
        )
    elif replica_identity != "default":
        statements.append(f"ALTER TABLE {qualified_table} REPLICA IDENTITY {replica_identity.upper()}")
    if replication["publication_name"] and replication["managed"]:
        publish_clause = ",".join(replication["publish_operations"])
        publication_name = replication["publication_name"]
        statements.append(
            f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = {_quote_literal(publication_name)}) THEN
        EXECUTE 'CREATE PUBLICATION {_quote_identifier(publication_name)} WITH (publish = ''{publish_clause}'')';
    END IF;
END
$$
""".strip()
        )
        statements.append(
            f"ALTER PUBLICATION {_quote_identifier(publication_name)} SET (publish = '{publish_clause}')"
        )
        statements.append(
            f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_publication_tables
        WHERE pubname = {_quote_literal(publication_name)}
          AND schemaname = {_quote_literal(schema)}
          AND tablename = {_quote_literal(table_name)}
    ) THEN
        EXECUTE 'ALTER PUBLICATION {_quote_identifier(publication_name)} ADD TABLE {qualified_table}';
    END IF;
END
$$
""".strip()
        )
    return statements


def _build_notification_payload_expression(payload_columns: list[str]) -> str:
    if not payload_columns:
        return "CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END"
    payload_pairs: list[str] = []
    for column in payload_columns:
        payload_pairs.append(_quote_literal(column))
        payload_pairs.append(
            f"CASE WHEN TG_OP = 'DELETE' THEN OLD.{_quote_identifier(column)} ELSE NEW.{_quote_identifier(column)} END"
        )
    return f"jsonb_build_object({', '.join(payload_pairs)})"


def _build_listen_notify_statements(schema: str, table_name: str, listen_notify: list[dict[str, Any]]) -> list[str]:
    qualified_table = _qualified_table(schema, table_name)
    statements: list[str] = []
    for item in listen_notify:
        function_name = _build_runtime_identifier("pb_notify_fn", table_name, item["channel"])
        trigger_name = _build_runtime_identifier("pb_notify_trg", table_name, item["channel"])
        payload_expression = _build_notification_payload_expression(item["payload_columns"])
        timing_events = " OR ".join(event.upper() for event in item["events"])
        statements.append(
            f"""
CREATE OR REPLACE FUNCTION {_qualified_table(schema, function_name)}() RETURNS trigger AS $$
DECLARE
    payload jsonb;
BEGIN
    payload := jsonb_build_object(
        'operation', lower(TG_OP),
        'schema', TG_TABLE_SCHEMA,
        'table', TG_TABLE_NAME,
        'data', {payload_expression}
    );
    PERFORM pg_notify({_quote_literal(item['channel'])}, payload::text);
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql
""".strip()
        )
        statements.append(f"DROP TRIGGER IF EXISTS {_quote_identifier(trigger_name)} ON {qualified_table}")
        statements.append(
            f"""
CREATE TRIGGER {_quote_identifier(trigger_name)}
AFTER {timing_events} ON {qualified_table}
FOR EACH ROW EXECUTE FUNCTION {_qualified_table(schema, function_name)}()
""".strip()
        )
    return statements


def build_postgres_table_plan(
    *,
    schema: str,
    table_name: str,
    columns: list[dict[str, Any]],
    advanced_features: dict[str, Any] | None = None,
) -> PostgresTablePlan:
    normalized_columns = normalize_table_columns(columns)
    normalized_advanced_features = normalize_postgres_advanced_features(
        table_name=table_name,
        normalized_columns=normalized_columns,
        advanced_features=advanced_features,
    )
    partitioning = normalized_advanced_features.get("partitioning")
    statements: list[str] = []
    for extension in normalized_advanced_features.get("extensions", []):
        statements.append(f"CREATE EXTENSION IF NOT EXISTS {_quote_identifier(extension)}")

    qualified_table = _qualified_table(schema, table_name)
    column_definitions = _build_column_definitions(normalized_columns=normalized_columns, partitioning=partitioning)
    statements.append(
        f"CREATE TABLE IF NOT EXISTS {qualified_table} ({', '.join(column_definitions)}){_build_partition_clause(partitioning)}"
    )
    statements.extend(_build_partition_statements(schema, table_name, partitioning))
    statements.extend(_build_index_statements(schema, table_name, normalized_advanced_features.get("indexes", [])))
    statements.extend(_build_replication_statements(schema, table_name, normalized_advanced_features.get("replication")))
    statements.extend(
        _build_listen_notify_statements(schema, table_name, normalized_advanced_features.get("listen_notify", []))
    )

    return PostgresTablePlan(
        normalized_columns=[
            {
                key: value
                for key, value in column.items()
                if key in {"name", "type", "nullable", "primary_key"}
            }
            for column in normalized_columns
        ],
        normalized_advanced_features=normalized_advanced_features,
        statements=statements,
        applied_sql=";\n".join(statements),
    )
