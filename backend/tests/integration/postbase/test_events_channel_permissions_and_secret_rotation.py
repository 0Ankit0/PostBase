from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import encode_id
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole
from src.postbase.domain.models import Subscription


async def _create_service_key(client, db_session, *, suffix: str) -> tuple[str, str]:
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

    owner = (await db_session.execute(select(User).where(User.email == f"events_owner_{suffix}@example.com"))).scalars().first()
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant_{suffix}", description="Events tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={"tenant_id": encode_id(tenant.id), "name": f"Events {suffix}", "slug": f"events_{suffix}", "description": "Events project"},
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

    return service_key_response.json()["plaintext_key"], str(tenant.id)


@pytest.mark.asyncio
async def test_channel_publish_denied_by_scoped_policy(client, db_session):
    service_key, _ = await _create_service_key(client, db_session, suffix="policy_deny")

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "secure", "description": "Secure", "policy_template": "read_only"},
    )
    assert channel_response.status_code == 200, channel_response.text

    publish_response = await client.post(
        f"/api/v1/events/publish/{channel_response.json()['id']}",
        headers={"X-PostBase-Key": service_key},
        json={"event_name": "deploy.blocked", "payload": {"id": "evt"}},
    )
    assert publish_response.status_code == 403, publish_response.text


@pytest.mark.asyncio
async def test_channel_isolation_between_environments(client, db_session):
    service_key_a, _ = await _create_service_key(client, db_session, suffix="isolation_a")
    service_key_b, _ = await _create_service_key(client, db_session, suffix="isolation_b")

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key_a},
        json={"channel_key": "isolated", "description": "A"},
    )
    assert channel_response.status_code == 200, channel_response.text

    cross_environment = await client.get(
        f"/api/v1/events/channels/{channel_response.json()['id']}",
        headers={"X-PostBase-Key": service_key_b},
    )
    assert cross_environment.status_code == 404, cross_environment.text


@pytest.mark.asyncio
async def test_webhook_secret_rotation_has_dual_secret_no_downtime(client, db_session):
    service_key, tenant_id = await _create_service_key(client, db_session, suffix="dual_secret")

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "rotations", "description": "rotations"},
    )
    channel_id = channel_response.json()["id"]

    create_webhook = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={
            "target_type": "webhook",
            "target_ref": "https://hooks.example.com/require-secret:alpha",
            "config_json": {
                "tenant_id": int(tenant_id),
                "signature": {"secret_ref": "events/signing", "algorithm": "sha256"},
                "endpoint_secrets": {"active": "alpha"},
            },
        },
    )
    assert create_webhook.status_code == 200, create_webhook.text
    subscription_id = create_webhook.json()["id"]

    rotate = await client.post(
        f"/api/v1/events/webhook-endpoints/{subscription_id}/rotate-secret",
        headers={"X-PostBase-Key": service_key},
        json={"new_secret": "beta", "grace_window_seconds": 600},
    )
    assert rotate.status_code == 200, rotate.text
    assert rotate.json()["has_previous_secret"] is True

    publish_during_grace = await client.post(
        f"/api/v1/events/publish/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"event_name": "deploy.rotated", "payload": {"id": "evt_grace"}},
    )
    assert publish_during_grace.status_code == 200, publish_during_grace.text
    statuses = [item["status"] for item in publish_during_grace.json()]
    assert "delivered" in statuses

    subscription = await db_session.get(Subscription, subscription_id)
    endpoint_secrets = dict(subscription.config_json.get("endpoint_secrets") or {})
    endpoint_secrets["previous_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    subscription.config_json = {**subscription.config_json, "endpoint_secrets": endpoint_secrets}
    await db_session.commit()

    publish_after_expiry = await client.post(
        f"/api/v1/events/publish/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"event_name": "deploy.expired", "payload": {"id": "evt_expired"}},
    )
    assert publish_after_expiry.status_code == 200, publish_after_expiry.text
    statuses = [item["status"] for item in publish_after_expiry.json()]
    assert "delivered" not in statuses
