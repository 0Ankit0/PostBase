from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import encode_id
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole
from src.postbase.domain.models import DataNamespace, SchemaMigration, TableDefinition


async def _bootstrap_advanced_context(client, db_session, *, suffix: str) -> dict[str, str]:
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": f"pg_adv_{suffix}",
            "email": f"pg-adv-{suffix}@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}

    owner = (
        await db_session.execute(select(User).where(User.email == f"pg-adv-{suffix}@example.com"))
    ).scalars().first()
    tenant = Tenant(name=f"PG Adv {suffix}", slug=f"pg-adv-{suffix}", description="postgres advanced", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": f"PG Advanced {suffix}",
            "slug": f"pg_advanced_{suffix}",
            "description": "postgres advanced",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Development", "slug": f"dev-{suffix}", "stage": "development"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    namespace_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces",
        headers=owner_headers,
        json={"name": "runtime"},
    )
    assert namespace_response.status_code == 201, namespace_response.text
    namespace_id = namespace_response.json()["id"]

    service_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "backend_service", "role": "service_role"},
    )
    assert service_key_response.status_code == 200, service_key_response.text

    return {
        "environment_id": environment_id,
        "namespace_id": namespace_id,
        "owner_auth": owner_headers["Authorization"],
        "service_key": service_key_response.json()["plaintext_key"],
    }


@pytest.mark.asyncio
async def test_provider_catalog_exposes_advanced_postgres_capabilities(client, db_session):
    context = await _bootstrap_advanced_context(client, db_session, suffix="catalog")
    catalog_response = await client.get(
        "/api/v1/provider-catalog",
        headers={"Authorization": context["owner_auth"]},
    )
    assert catalog_response.status_code == 200, catalog_response.text

    data_provider = next(
        item
        for item in catalog_response.json()["items"]
        if item["capability_key"] == "data" and item["provider_key"] == "postgres-native"
    )
    optional_features = set(data_provider["metadata_json"]["optional_features"])
    assert {
        "extensions",
        "indexes",
        "partitioning",
        "sharding",
        "replication",
        "listen_notify",
    }.issubset(optional_features)


@pytest.mark.asyncio
async def test_advanced_postgres_table_provisioning_persists_manifest_and_supports_data_api(client, db_session):
    context = await _bootstrap_advanced_context(client, db_session, suffix="runtime")
    table_response = await client.post(
        f"/api/v1/environments/{context['environment_id']}/data/namespaces/{context['namespace_id']}/tables",
        headers={"Authorization": context["owner_auth"]},
        json={
            "table_name": "audit_events",
            "columns": [
                {"name": "tenant_id", "type": "integer", "nullable": False},
                {"name": "created_at", "type": "datetime", "nullable": False},
                {"name": "title", "type": "citext", "nullable": False},
            ],
            "policy_mode": "public",
            "advanced_features": {
                "indexes": [
                    {
                        "name": "ix_audit_tenant_created",
                        "columns": ["tenant_id", "created_at"],
                        "method": "btree",
                    }
                ],
                "partitioning": {
                    "strategy": "range",
                    "columns": ["created_at"],
                    "partitions": [
                        {"name": "audit_events_2026_h1", "from_value": "2026-01-01", "to_value": "2026-07-01"},
                        {"name": "audit_events_2026_h2", "from_value": "2026-07-01", "to_value": "2027-01-01"},
                    ],
                },
                "sharding": {
                    "strategy": "logical",
                    "shard_key": "tenant_id",
                    "shard_count": 8,
                },
                "replication": {
                    "mode": "logical",
                    "publication_name": "audit_events_pub",
                    "publish_operations": ["insert", "update", "delete"],
                },
                "listen_notify": [
                    {
                        "channel": "audit_runtime",
                        "events": ["insert", "update"],
                        "payload_columns": ["tenant_id", "title"],
                    }
                ],
            },
        },
    )
    assert table_response.status_code == 201, table_response.text
    table_payload = table_response.json()
    assert set(table_payload["advanced_features_json"]["integration_manifest"]["postgres_capabilities"]) == {
        "extensions",
        "indexes",
        "listen_notify",
        "partitioning",
        "replication",
        "sharding",
    }
    assert table_payload["advanced_features_json"]["integration_manifest"]["notifications"][0]["listen_command"] == (
        "LISTEN audit_runtime;"
    )
    assert table_payload["advanced_features_json"]["integration_manifest"]["replication"]["requires_external_setup"] is True

    create_row_response = await client.post(
        "/api/v1/data/runtime/audit_events",
        headers={"X-PostBase-Key": context["service_key"]},
        json={
            "values": {
                "tenant_id": 42,
                "created_at": "2026-02-15T10:00:00",
                "title": "Provisioned",
            }
        },
    )
    assert create_row_response.status_code == 200, create_row_response.text

    list_rows_response = await client.get(
        "/api/v1/data/runtime/audit_events",
        headers={"X-PostBase-Key": context["service_key"]},
    )
    assert list_rows_response.status_code == 200, list_rows_response.text
    assert list_rows_response.json()["items"][0]["title"] == "Provisioned"

    namespace_row = (
        await db_session.execute(select(DataNamespace).where(DataNamespace.name == "runtime"))
    ).scalars().first()
    definition = (
        await db_session.execute(select(TableDefinition).where(TableDefinition.table_name == "audit_events"))
    ).scalars().first()
    migration = (
        await db_session.execute(
            select(SchemaMigration)
            .where(SchemaMigration.table_definition_id == definition.id)
            .order_by(SchemaMigration.id.desc())
        )
    ).scalars().first()

    assert namespace_row is not None
    assert definition is not None
    assert migration is not None
    assert "CREATE TABLE IF NOT EXISTS" in migration.applied_sql
    assert "PARTITION BY RANGE" in migration.applied_sql
    assert "pg_notify" in migration.applied_sql

    partition_rows = (
        await db_session.execute(
            text(
                """
                SELECT child.relname
                FROM pg_inherits
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid
                JOIN pg_namespace namespace_row ON namespace_row.oid = parent.relnamespace
                WHERE namespace_row.nspname = :schema_name
                  AND parent.relname = :table_name
                ORDER BY child.relname
                """
            ),
            {"schema_name": namespace_row.physical_schema, "table_name": "audit_events"},
        )
    ).scalars().all()
    assert partition_rows == ["audit_events_2026_h1", "audit_events_2026_h2"]

    trigger_count = (
        await db_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_trigger trigger_row
                JOIN pg_class table_row ON trigger_row.tgrelid = table_row.oid
                JOIN pg_namespace namespace_row ON namespace_row.oid = table_row.relnamespace
                WHERE namespace_row.nspname = :schema_name
                  AND table_row.relname = :table_name
                  AND trigger_row.tgname LIKE 'pb_notify_trg%'
                """
            ),
            {"schema_name": namespace_row.physical_schema, "table_name": "audit_events"},
        )
    ).scalar_one()
    assert trigger_count >= 1

    index_regclass = (
        await db_session.execute(
            text("SELECT to_regclass(:index_name)"),
            {"index_name": f'{namespace_row.physical_schema}.ix_audit_tenant_created'},
        )
    ).scalar_one()
    assert index_regclass is not None

    partition_target = (
        await db_session.execute(
            text(
                f"""
                SELECT tableoid::regclass::text
                FROM "{namespace_row.physical_schema}"."audit_events"
                LIMIT 1
                """
            )
        )
    ).scalar_one()
    assert partition_target.endswith("audit_events_2026_h1")
