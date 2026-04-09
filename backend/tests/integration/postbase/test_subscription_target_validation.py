import pytest
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import encode_id
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole


async def _create_service_key(client, db_session, *, suffix: str) -> str:
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": f"events_owner_{suffix}",
            "email": f"events_owner_{suffix}@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}

    owner = (
        await db_session.execute(select(User).where(User.email == f"events_owner_{suffix}@example.com"))
    ).scalars().first()
    tenant = Tenant(
        name=f"Tenant {suffix}",
        slug=f"tenant_{suffix}",
        description="Tenant for events subscription validation",
        owner_id=owner.id,
    )
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

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": f"Events {suffix}",
            "slug": f"events_{suffix}",
            "description": "Events project",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Production", "slug": "prod", "stage": "production"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    service_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "events_service", "role": "service_role"},
    )
    assert service_key_response.status_code == 200, service_key_response.text

    return service_key_response.json()["plaintext_key"], tenant.id


@pytest.mark.asyncio
async def test_subscription_target_validation_accepts_valid_room_and_webhook(client, db_session):
    service_key, tenant_id = await _create_service_key(client, db_session, suffix="valid_targets")

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "deployments", "description": "Deployment stream"},
    )
    assert channel_response.status_code == 200, channel_response.text
    channel_id = channel_response.json()["id"]

    room_subscription_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"target_type": "room", "target_ref": "Deployments-Room", "config_json": {}},
    )
    assert room_subscription_response.status_code == 200, room_subscription_response.text
    assert room_subscription_response.json()["target_ref"] == "deployments_room"

    webhook_subscription_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={
            "target_type": "webhook",
            "target_ref": "https://hooks.example.com/events",
            "config_json": {
                "tenant_id": tenant_id,
                "signature": {"secret_ref": "events/webhook-signing-key", "algorithm": "sha256"},
            },
        },
    )
    assert webhook_subscription_response.status_code == 200, webhook_subscription_response.text


@pytest.mark.asyncio
async def test_subscription_target_validation_rejects_invalid_configurations(client, db_session):
    service_key, tenant_id = await _create_service_key(client, db_session, suffix="invalid_targets")

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "alerts", "description": "Alert stream"},
    )
    assert channel_response.status_code == 200, channel_response.text
    channel_id = channel_response.json()["id"]

    non_https_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"target_type": "webhook", "target_ref": "http://hooks.example.com/events", "config_json": {}},
    )
    assert non_https_response.status_code == 400, non_https_response.text

    missing_signature_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={
            "target_type": "webhook",
            "target_ref": "https://hooks.example.com/events",
            "config_json": {"tenant_id": tenant_id},
        },
    )
    assert missing_signature_response.status_code == 400, missing_signature_response.text

    cross_tenant_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={
            "target_type": "room",
            "target_ref": "alerts",
            "config_json": {"tenant_id": tenant_id + 999},
        },
    )
    assert cross_tenant_response.status_code == 400, cross_tenant_response.text


@pytest.mark.asyncio
async def test_subscription_update_enforces_target_validation(client, db_session):
    service_key, tenant_id = await _create_service_key(client, db_session, suffix="update_targets")

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "ops", "description": "Ops stream"},
    )
    assert channel_response.status_code == 200, channel_response.text
    channel_id = channel_response.json()["id"]

    create_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"target_type": "room", "target_ref": "ops_room", "config_json": {"tenant_id": tenant_id}},
    )
    assert create_response.status_code == 200, create_response.text
    subscription_id = create_response.json()["id"]

    invalid_update = await client.patch(
        f"/api/v1/events/subscriptions/{subscription_id}",
        headers={"X-PostBase-Key": service_key},
        json={
            "target_type": "webhook",
            "target_ref": "https://hooks.example.com/ops",
            "config_json": {"signature": {"algorithm": "sha256"}},
        },
    )
    assert invalid_update.status_code == 400, invalid_update.text

    valid_update = await client.patch(
        f"/api/v1/events/subscriptions/{subscription_id}",
        headers={"X-PostBase-Key": service_key},
        json={
            "target_type": "webhook",
            "target_ref": "https://hooks.example.com/ops",
            "config_json": {
                "tenant_id": tenant_id,
                "signature": {"secret_ref": "events/ops-signing-key", "algorithm": "sha512"},
            },
        },
    )
    assert valid_update.status_code == 200, valid_update.text
    assert valid_update.json()["target_type"] == "webhook"
