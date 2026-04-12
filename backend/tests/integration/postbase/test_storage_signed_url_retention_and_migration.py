import base64
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import encode_id
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole
from src.postbase.domain.models import FileObject, StorageSignedUrlGrant


async def _bootstrap_storage_context(client, db_session, *, suffix: str):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": f"storage_owner_{suffix}",
            "email": f"storage-owner-{suffix}@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}

    owner = (await db_session.execute(select(User).where(User.email == f"storage-owner-{suffix}@example.com"))).scalars().first()
    tenant = Tenant(name=f"Storage {suffix}", slug=f"storage-{suffix}", description="Storage tests", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={"tenant_id": encode_id(tenant.id), "name": f"Storage {suffix}", "slug": f"storage-{suffix}", "description": "Storage tests"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Staging", "slug": f"stg-{suffix}", "stage": "staging"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    anon_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "web", "role": "anon"},
    )
    assert anon_key_response.status_code == 200, anon_key_response.text
    anon_key = anon_key_response.json()["plaintext_key"]

    auth_signup_response = await client.post(
        "/api/v1/auth/users",
        headers={"X-PostBase-Key": anon_key},
        json={"username": f"storage_user_{suffix}", "email": f"storage-user-{suffix}@example.com", "password": "UserPass123!"},
    )
    assert auth_signup_response.status_code == 200, auth_signup_response.text
    access_token = auth_signup_response.json()["tokens"]["access_token"]
    user_headers = {"Authorization": f"Bearer {access_token}"}
    return owner_headers, user_headers, environment_id


@pytest.mark.asyncio
async def test_signed_url_issue_refresh_revoke_with_expiry_enforcement(client, db_session):
    _, user_headers, _ = await _bootstrap_storage_context(client, db_session, suffix="signed")

    upload_response = await client.post(
        "/api/v1/storage/files",
        headers=user_headers,
        json={
            "filename": "signed.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"hello signed url").decode("utf-8"),
            "bucket_key": "assets",
            "namespace": "public",
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    file_id = upload_response.json()["id"]

    issue_response = await client.post(
        f"/api/v1/storage/files/{file_id}/signed-urls",
        headers=user_headers,
        json={"access_mode": "read", "expires_in_seconds": 120},
    )
    assert issue_response.status_code == 200, issue_response.text
    grant_id = issue_response.json()["grant_id"]
    assert issue_response.json()["token"]

    refresh_response = await client.post(
        f"/api/v1/storage/signed-urls/{grant_id}/refresh",
        headers=user_headers,
        json={"access_mode": "read", "expires_in_seconds": 120},
    )
    assert refresh_response.status_code == 200, refresh_response.text

    new_grant_id = refresh_response.json()["grant_id"]
    grant = await db_session.get(StorageSignedUrlGrant, int(new_grant_id))
    grant.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    expired_refresh_response = await client.post(
        f"/api/v1/storage/signed-urls/{new_grant_id}/refresh",
        headers=user_headers,
        json={"access_mode": "read", "expires_in_seconds": 120},
    )
    assert expired_refresh_response.status_code == 410, expired_refresh_response.text

    revoke_response = await client.delete(f"/api/v1/storage/signed-urls/{new_grant_id}", headers=user_headers)
    assert revoke_response.status_code == 204, revoke_response.text


@pytest.mark.asyncio
async def test_storage_retention_rule_execution_cleans_expired_files(client, db_session):
    _, user_headers, _ = await _bootstrap_storage_context(client, db_session, suffix="retention")

    upload_response = await client.post(
        "/api/v1/storage/files",
        headers=user_headers,
        json={
            "filename": "old.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"old file").decode("utf-8"),
            "bucket_key": "archive",
            "namespace": "logs",
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    file_id = upload_response.json()["id"]

    metadata_response = await client.get(f"/api/v1/storage/files/{file_id}/metadata", headers=user_headers)
    assert metadata_response.status_code == 200, metadata_response.text

    persisted = await db_session.get(FileObject, int(file_id))
    persisted.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db_session.commit()

    rule_response = await client.post(
        "/api/v1/storage/retention/rules",
        headers=user_headers,
        json={"bucket_key": "archive", "namespace": "logs", "max_age_days": 1, "sweep_interval_minutes": 60, "enabled": True},
    )
    assert rule_response.status_code == 200, rule_response.text

    run_response = await client.post("/api/v1/storage/retention/run", headers=user_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["deleted_files"] >= 1

    list_response = await client.get("/api/v1/storage/files?bucket_key=archive", headers=user_headers)
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["total"] == 0


@pytest.mark.asyncio
async def test_storage_provider_switchover_tracks_copy_and_cutover_checkpoints(client, db_session):
    owner_headers, user_headers, environment_id = await _bootstrap_storage_context(client, db_session, suffix="switch")

    upload_response = await client.post(
        "/api/v1/storage/files",
        headers=user_headers,
        json={
            "filename": "switch.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"for switchover").decode("utf-8"),
            "bucket_key": "assets",
            "namespace": "public",
        },
    )
    assert upload_response.status_code == 200, upload_response.text

    bindings_response = await client.get(f"/api/v1/environments/{environment_id}/bindings", headers=owner_headers)
    assert bindings_response.status_code == 200, bindings_response.text
    storage_binding = next(item for item in bindings_response.json() if item["capability_key"] == "storage")

    switchover_response = await client.post(
        f"/api/v1/bindings/{storage_binding['id']}/switchovers",
        headers=owner_headers,
        json={"target_provider_key": "s3-compatible", "strategy": "cutover", "retirement_strategy": "manual"},
    )
    assert switchover_response.status_code == 200, switchover_response.text

    execute_response = await client.post(
        f"/api/v1/switchovers/{switchover_response.json()['id']}/execute",
        headers=owner_headers,
    )
    assert execute_response.status_code == 200, execute_response.text
    payload = execute_response.json()
    execution_state = payload.get("execution_state_json") or {}
    assert payload["status"] == "completed"
    assert "data_copy_job" in execution_state
    assert execution_state.get("cutover_checkpoints", {}).get("signed_url_issuance") == "verified"
