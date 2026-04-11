import pytest
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import encode_id
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole


async def _signup(client, *, username: str, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": username,
            "email": email,
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access']}"}


@pytest.mark.asyncio
async def test_list_projects_applies_offset_limit_and_access_scope(client, db_session):
    owner_headers = await _signup(client, username="owner_one", email="owner_one@example.com")
    outsider_headers = await _signup(client, username="owner_two", email="owner_two@example.com")

    owner = (await db_session.execute(select(User).where(User.email == "owner_one@example.com"))).scalars().one()
    outsider = (await db_session.execute(select(User).where(User.email == "owner_two@example.com"))).scalars().one()

    owner_tenant = Tenant(name="Owner Tenant", slug="owner-tenant", description="owner", owner_id=owner.id)
    outsider_tenant = Tenant(name="Outsider Tenant", slug="outsider-tenant", description="outsider", owner_id=outsider.id)
    db_session.add(owner_tenant)
    db_session.add(outsider_tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=owner_tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    db_session.add(TenantMember(tenant_id=outsider_tenant.id, user_id=outsider.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    owner_tenant_hash = encode_id(owner_tenant.id)
    outsider_tenant_hash = encode_id(outsider_tenant.id)

    for idx in range(3):
        response = await client.post(
            "/api/v1/projects",
            headers=owner_headers,
            json={
                "tenant_id": owner_tenant_hash,
                "name": f"Owner Project {idx}",
                "slug": f"owner_project_{idx}",
                "description": "visible",
            },
        )
        assert response.status_code == 201, response.text

    outsider_project_response = await client.post(
        "/api/v1/projects",
        headers=outsider_headers,
        json={
            "tenant_id": outsider_tenant_hash,
            "name": "Outsider Project",
            "slug": "outsider_project",
            "description": "hidden",
        },
    )
    assert outsider_project_response.status_code == 201, outsider_project_response.text

    page_one = await client.get("/api/v1/projects?skip=0&limit=2", headers=owner_headers)
    assert page_one.status_code == 200, page_one.text
    page_one_payload = page_one.json()
    assert page_one_payload["total"] == 3
    assert page_one_payload["skip"] == 0
    assert page_one_payload["limit"] == 2
    assert len(page_one_payload["items"]) == 2

    page_two = await client.get("/api/v1/projects?skip=2&limit=2", headers=owner_headers)
    assert page_two.status_code == 200, page_two.text
    page_two_payload = page_two.json()
    assert page_two_payload["total"] == 3
    assert page_two_payload["skip"] == 2
    assert page_two_payload["limit"] == 2
    assert len(page_two_payload["items"]) == 1

    outsider_view = await client.get("/api/v1/projects?skip=0&limit=10", headers=owner_headers)
    assert outsider_view.status_code == 200, outsider_view.text
    assert all(item["name"].startswith("Owner Project") for item in outsider_view.json()["items"])


@pytest.mark.asyncio
async def test_list_routes_return_paginated_envelopes_and_respect_bounds(client, db_session):
    owner_headers = await _signup(client, username="ops_owner", email="ops_owner@example.com")
    owner = (await db_session.execute(select(User).where(User.email == "ops_owner@example.com"))).scalars().one()

    tenant = Tenant(name="Ops Tenant", slug="ops-tenant", description="ops", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    tenant_hash = encode_id(tenant.id)
    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={"tenant_id": tenant_hash, "name": "Ops Project", "slug": "ops_project", "description": "ops"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    for idx in range(3):
        environment_response = await client.post(
            f"/api/v1/projects/{project_id}/environments",
            headers=owner_headers,
            json={"name": f"Env {idx}", "slug": f"env_{idx}", "stage": "development"},
        )
        assert environment_response.status_code == 201, environment_response.text

    environments_page = await client.get(
        f"/api/v1/projects/{project_id}/environments?skip=1&limit=1",
        headers=owner_headers,
    )
    assert environments_page.status_code == 200, environments_page.text
    payload = environments_page.json()
    assert payload["total"] == 3
    assert payload["skip"] == 1
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1

    first_environment_id = payload["items"][0]["id"]

    # Bounds checking should reject out-of-range limits.
    invalid_limit = await client.get(
        f"/api/v1/environments/{first_environment_id}/bindings?skip=0&limit=101",
        headers=owner_headers,
    )
    assert invalid_limit.status_code == 422, invalid_limit.text

    for endpoint in (
        f"/api/v1/environments/{first_environment_id}/bindings?skip=0&limit=10",
        f"/api/v1/environments/{first_environment_id}/secrets?skip=0&limit=10",
        f"/api/v1/environments/{first_environment_id}/migrations?skip=0&limit=10",
        f"/api/v1/projects/{project_id}/usage?skip=0&limit=10",
        f"/api/v1/projects/{project_id}/audit?skip=0&limit=10",
    ):
        response = await client.get(endpoint, headers=owner_headers)
        assert response.status_code == 200, response.text
        list_payload = response.json()
        assert set(list_payload.keys()) >= {"items", "total", "skip", "limit"}
        assert list_payload["skip"] == 0
        assert list_payload["limit"] == 10


@pytest.mark.asyncio
async def test_pagination_boundaries_empty_last_and_large_total(client, db_session):
    owner_headers = await _signup(client, username="boundary_owner", email="boundary_owner@example.com")
    owner = (await db_session.execute(select(User).where(User.email == "boundary_owner@example.com"))).scalars().one()

    tenant = Tenant(name="Boundary Tenant", slug="boundary-tenant", description="boundary", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    tenant_hash = encode_id(tenant.id)
    for idx in range(105):
        response = await client.post(
            "/api/v1/projects",
            headers=owner_headers,
            json={
                "tenant_id": tenant_hash,
                "name": f"Boundary Project {idx}",
                "slug": f"boundary_project_{idx}",
                "description": "pagination boundary",
            },
        )
        assert response.status_code == 201, response.text

    empty_page = await client.get("/api/v1/projects?skip=500&limit=25", headers=owner_headers)
    assert empty_page.status_code == 200, empty_page.text
    assert empty_page.json()["items"] == []
    assert empty_page.json()["total"] == 105

    last_page = await client.get("/api/v1/projects?skip=100&limit=25", headers=owner_headers)
    assert last_page.status_code == 200, last_page.text
    assert len(last_page.json()["items"]) == 5
    assert last_page.json()["total"] == 105
