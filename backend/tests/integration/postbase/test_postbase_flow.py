import pytest
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole


async def _create_service_key(client, db_session, *, suffix: str) -> str:
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": f"query_owner_{suffix}",
            "email": f"query_owner_{suffix}@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}

    owner = (
        await db_session.execute(select(User).where(User.email == f"query_owner_{suffix}@example.com"))
    ).scalars().first()
    tenant = Tenant(name=f"Query {suffix}", slug=f"query-{suffix}", description="Query tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    from src.apps.iam.utils.hashid import encode_id

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": f"Query Project {suffix}",
            "slug": f"query_project_{suffix}",
            "description": "Query project",
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

    service_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "query_service", "role": "service_role"},
    )
    assert service_key_response.status_code == 200, service_key_response.text
    return service_key_response.json()["plaintext_key"]


@pytest.mark.asyncio
async def test_postbase_control_plane_and_auth_data_flow(client, db_session):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": "platform_owner",
            "email": "owner@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_access = signup_response.json()["access"]
    owner_headers = {"Authorization": f"Bearer {owner_access}"}

    owner = (
        await db_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalars().first()
    tenant = Tenant(name="Acme", slug="acme", description="Acme tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        TenantMember(
            tenant_id=tenant.id,
            user_id=owner.id,
            role=TenantRole.OWNER,
            is_active=True,
        )
    )
    await db_session.commit()

    tenant_id = tenant.id
    from src.apps.iam.utils.hashid import encode_id

    tenant_hash = encode_id(tenant_id)

    catalog_response = await client.get("/api/v1/provider-catalog", headers=owner_headers)
    assert catalog_response.status_code == 200, catalog_response.text
    provider_items = catalog_response.json()["items"]
    provider_keys = {(item["capability_key"], item["provider_key"]) for item in provider_items}
    assert ("auth", "local-postgres") in provider_keys
    assert ("data", "postgres-native") in provider_keys
    assert ("storage", "local-disk") in provider_keys
    assert ("functions", "inline-runtime") in provider_keys
    assert ("events", "websocket-gateway") in provider_keys

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": tenant_hash,
            "name": "Main Project",
            "slug": "main_project",
            "description": "Primary project",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Development", "slug": "dev", "stage": "development"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "client_anon", "role": "anon"},
    )
    assert key_response.status_code == 200, key_response.text
    anon_key = key_response.json()["plaintext_key"]

    namespace_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces",
        headers=owner_headers,
        json={"name": "app"},
    )
    assert namespace_response.status_code == 201, namespace_response.text
    namespace = namespace_response.json()

    table_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces/{namespace['id']}/tables",
        headers=owner_headers,
        json={
            "table_name": "posts",
            "columns": [
                {"name": "title", "type": "string", "nullable": False},
                {"name": "auth_user_id", "type": "integer", "nullable": False},
            ],
            "policy_mode": "owner",
            "owner_column": "auth_user_id",
        },
    )
    assert table_response.status_code == 201, table_response.text

    auth_signup_response = await client.post(
        "/api/v1/auth/users",
        headers={"X-PostBase-Key": anon_key},
        json={
            "username": "app_user",
            "email": "app@example.com",
            "password": "AppUser123!",
        },
    )
    assert auth_signup_response.status_code == 200, auth_signup_response.text
    tokens = auth_signup_response.json()["tokens"]
    access_token = tokens["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 200, me_response.text
    me_payload = me_response.json()
    assert me_payload["email"] == "app@example.com"

    create_row_response = await client.post(
        "/api/v1/data/app/posts",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"values": {"title": "hello world"}},
    )
    assert create_row_response.status_code == 200, create_row_response.text

    list_rows_response = await client.get(
        "/api/v1/data/app/posts",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert list_rows_response.status_code == 200, list_rows_response.text
    rows = list_rows_response.json()["items"]
    assert len(rows) == 1
    assert rows[0]["title"] == "hello world"

    query_rows_response = await client.post(
        "/api/v1/data/query",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "namespace": "app",
            "table": "posts",
            "filters": {"title": "hello world"},
            "limit": 10,
            "offset": 0,
            "order_by": "id",
            "order_direction": "asc",
        },
    )
    assert query_rows_response.status_code == 200, query_rows_response.text
    queried_rows = query_rows_response.json()["rows"]
    assert len(queried_rows) == 1
    assert queried_rows[0]["title"] == "hello world"


@pytest.mark.asyncio
async def test_data_query_rejects_unsupported_filter_operator(client, db_session):
    service_key = await _create_service_key(client, db_session, suffix="invalid-filter")
    response = await client.post(
        "/api/v1/data/query",
        headers={"X-PostBase-Key": service_key},
        json={
            "namespace": "app",
            "table": "posts",
            "filters": [{"field": "title", "op": "regex", "value": "h.*"}],
            "pagination": {"limit": 10, "offset": 0},
            "sort": [],
        },
    )
    assert response.status_code in {400, 422}
