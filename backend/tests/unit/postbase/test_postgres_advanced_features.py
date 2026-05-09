from src.postbase.providers.data.postgres_advanced import build_postgres_table_plan


def test_postgres_table_plan_derives_hash_shards_and_replication_sql():
    plan = build_postgres_table_plan(
        schema="pb_runtime",
        table_name="event_stream",
        columns=[
            {"name": "tenant_id", "type": "integer", "nullable": False},
            {"name": "payload", "type": "jsonb", "nullable": False},
        ],
        advanced_features={
            "sharding": {
                "strategy": "native_hash_partitioning",
                "shard_key": "tenant_id",
                "shard_count": 4,
            },
            "replication": {
                "mode": "logical",
                "managed": True,
                "publication_name": "event_stream_pub",
                "publish_operations": ["insert", "update"],
                "replica_identity": "full",
            },
            "listen_notify": [
                {
                    "channel": "event_runtime",
                    "events": ["insert"],
                    "payload_columns": ["tenant_id"],
                }
            ],
        },
    )

    assert plan.normalized_advanced_features["partitioning"]["strategy"] == "hash"
    assert plan.normalized_advanced_features["partitioning"]["partition_count"] == 4
    assert plan.normalized_advanced_features["sharding"]["strategy"] == "native_hash_partitioning"
    assert plan.normalized_advanced_features["integration_manifest"]["notifications"][0]["listen_command"] == (
        "LISTEN event_runtime;"
    )
    assert any("PARTITION BY HASH" in statement for statement in plan.statements)
    assert any("CREATE PUBLICATION" in statement for statement in plan.statements)
    assert any("pg_notify" in statement for statement in plan.statements)


def test_postgres_table_plan_preserves_explicit_id_column_without_synthesizing_bigserial():
    plan = build_postgres_table_plan(
        schema="pb_runtime",
        table_name="deployments",
        columns=[
            {"name": "id", "type": "uuid", "nullable": False, "primary_key": True},
        ],
    )

    assert plan.normalized_columns == [{"name": "id", "type": "uuid", "nullable": False, "primary_key": True}]
    assert plan.statements == [
        'CREATE TABLE IF NOT EXISTS "pb_runtime"."deployments" ("id" UUID PRIMARY KEY)'
    ]
