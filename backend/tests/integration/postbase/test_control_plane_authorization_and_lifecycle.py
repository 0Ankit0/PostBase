import pytest
from sqlmodel import select
from uuid import uuid4

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import encode_id
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole
from src.postbase.domain.models import ProviderCatalogEntry


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


async def _setup_project_environment(client, db_session):
    suffix = uuid4().hex[:8]
    owner_email = f"cp_owner_{suffix}@example.com"
    member_email = f"cp_member_{suffix}@example.com"
    owner_headers = await _signup(client, username=f"cp_owner_{suffix}", email=owner_email)
    member_headers = await _signup(client, username=f"cp_member_{suffix}", email=member_email)
    owner = (await db_session.execute(select(User).where(User.email == owner_email))).scalars().first()
    member = (await db_session.execute(select(User).where(User.email == member_email))).scalars().first()
    tenant = Tenant(name=f"cp-{suffix}", slug=f"cp-{suffix}", description="cp tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=member.id, role=TenantRole.MEMBER, is_active=True))
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={"tenant_id": encode_id(tenant.id), "name": "CP", "slug": f"cp-project-{suffix}", "description": "control-plane"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]
    env_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Staging", "slug": f"staging-{suffix}", "stage": "staging"},
    )
    assert env_response.status_code == 201, env_response.text
    return owner_headers, member_headers, project_id, env_response.json()["id"]


@pytest.mark.asyncio
async def test_control_plane_rbac_allow_deny_matrix(client, db_session):
    owner_headers, member_headers, _, environment_id = await _setup_project_environment(client, db_session)

    allow_secret = await client.post(
        f"/api/v1/environments/{environment_id}/secrets",
        headers=owner_headers,
        json={"name": "svc", "provider_key": "s3-compatible", "secret_kind": "access_key", "secret_value": "abcd1234"},
    )
    assert allow_secret.status_code == 201, allow_secret.text

    deny_secret = await client.post(
        f"/api/v1/environments/{environment_id}/secrets",
        headers=member_headers,
        json={"name": "svc2", "provider_key": "s3-compatible", "secret_kind": "access_key", "secret_value": "abcd1234"},
    )
    assert deny_secret.status_code == 403, deny_secret.text
    assert deny_secret.json()["detail"]["code"] == "control_plane_forbidden"

    deny_binding = await client.post(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=member_headers,
        json={"capability_key": "storage", "provider_key": "s3-compatible", "config_json": {}, "secret_ref_ids": []},
    )
    assert deny_binding.status_code == 403, deny_binding.text


@pytest.mark.asyncio
async def test_binding_status_transitions_enforce_legal_matrix(client, db_session):
    owner_headers, _, _, environment_id = await _setup_project_environment(client, db_session)
    list_response = await client.get(f"/api/v1/environments/{environment_id}/bindings", headers=owner_headers)
    assert list_response.status_code == 200, list_response.text
    binding_id = list_response.json()["items"][0]["id"]

    valid_transition = await client.post(
        f"/api/v1/bindings/{binding_id}/status",
        headers=owner_headers,
        json={"status": "deprecated", "reason": "planned transition"},
    )
    assert valid_transition.status_code == 200, valid_transition.text
    assert valid_transition.json()["status"] == "deprecated"

    invalid_transition = await client.post(
        f"/api/v1/bindings/{binding_id}/status",
        headers=owner_headers,
        json={"status": "pending", "reason": "illegal transition"},
    )
    assert invalid_transition.status_code == 409, invalid_transition.text
    assert invalid_transition.json()["detail"]["code"] == "binding_invalid_status_transition"


@pytest.mark.asyncio
async def test_binding_activation_blocked_when_required_secret_missing(client, db_session):
    owner_headers, _, _, environment_id = await _setup_project_environment(client, db_session)
    provider = (
        await db_session.execute(select(ProviderCatalogEntry).where(ProviderCatalogEntry.provider_key == "s3-compatible"))
    ).scalars().first()
    assert provider is not None
    provider.metadata_json = {**provider.metadata_json, "required_secret_kinds": ["access_key"]}
    await db_session.commit()

    create_response = await client.post(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
        json={"capability_key": "storage", "provider_key": "s3-compatible", "config_json": {}, "secret_ref_ids": []},
    )
    assert create_response.status_code == 200, create_response.text
    binding_id = create_response.json()["id"]
    assert create_response.json()["status"] == "failed"

    activate_response = await client.post(
        f"/api/v1/bindings/{binding_id}/status",
        headers=owner_headers,
        json={"status": "active", "reason": "force-activate"},
    )
    assert activate_response.status_code == 409, activate_response.text
    assert "missing or expired secrets" in activate_response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_project_create_idempotency_replays_duplicate_submit(client, db_session):
    suffix = uuid4().hex[:8]
    owner_headers = await _signup(client, username=f"idem_owner_{suffix}", email=f"idem_owner_{suffix}@example.com")
    owner = (
        await db_session.execute(select(User).where(User.email == f"idem_owner_{suffix}@example.com"))
    ).scalars().first()
    tenant = Tenant(name=f"idem-{suffix}", slug=f"idem-{suffix}", description="idem tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    payload = {
        "tenant_id": encode_id(tenant.id),
        "name": "Idempotent Project",
        "slug": f"idem-project-{suffix}",
        "description": "first create",
    }
    idem_headers = {**owner_headers, "Idempotency-Key": f"project-create-{suffix}"}
    first = await client.post("/api/v1/projects", headers=idem_headers, json=payload)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/projects", headers=idem_headers, json=payload)
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_project_create_idempotency_rejects_conflicting_payload(client, db_session):
    suffix = uuid4().hex[:8]
    owner_headers = await _signup(client, username=f"idem_conf_owner_{suffix}", email=f"idem_conf_owner_{suffix}@example.com")
    owner = (
        await db_session.execute(select(User).where(User.email == f"idem_conf_owner_{suffix}@example.com"))
    ).scalars().first()
    tenant = Tenant(name=f"idemc-{suffix}", slug=f"idemc-{suffix}", description="idem tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    key_headers = {**owner_headers, "Idempotency-Key": f"project-create-conflict-{suffix}"}
    first_payload = {
        "tenant_id": encode_id(tenant.id),
        "name": "Conflict Project",
        "slug": f"idem-conf-{suffix}",
        "description": "first create",
    }
    second_payload = {
        "tenant_id": encode_id(tenant.id),
        "name": "Conflict Project Renamed",
        "slug": f"idem-conf-other-{suffix}",
        "description": "changed payload",
    }
    first = await client.post("/api/v1/projects", headers=key_headers, json=first_payload)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/projects", headers=key_headers, json=second_payload)
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "idempotency_key_payload_conflict"


@pytest.mark.asyncio
async def test_binding_status_idempotency_replays_duplicate_submit(client, db_session):
    owner_headers, _, _, environment_id = await _setup_project_environment(client, db_session)
    list_response = await client.get(f"/api/v1/environments/{environment_id}/bindings", headers=owner_headers)
    assert list_response.status_code == 200, list_response.text
    binding_id = list_response.json()["items"][0]["id"]
    idem_headers = {**owner_headers, "Idempotency-Key": f"binding-status-{uuid4().hex[:8]}"}
    payload = {"status": "deprecated", "reason": "planned transition"}

    first = await client.post(f"/api/v1/bindings/{binding_id}/status", headers=idem_headers, json=payload)
    assert first.status_code == 200, first.text
    second = await client.post(f"/api/v1/bindings/{binding_id}/status", headers=idem_headers, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == first.json()["status"]
