import pytest
from httpx import AsyncClient


async def _signup_and_get_token(client: AsyncClient, username: str, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": username,
            "email": email,
            "password": "TenantInvite123!",
            "confirm_password": "TenantInvite123!",
        },
    )
    assert response.status_code == 200
    return response.json()["access"]


@pytest.mark.asyncio
async def test_invitation_history_exposes_decision_timestamps_and_invitee_actions(
    client: AsyncClient,
):
    owner_token = await _signup_and_get_token(
        client,
        "tenant_owner_audit",
        "tenant_owner_audit@example.com",
    )
    invitee_token = await _signup_and_get_token(
        client,
        "tenant_invitee_audit",
        "tenant_invitee_audit@example.com",
    )

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    invitee_headers = {"Authorization": f"Bearer {invitee_token}"}

    tenant_response = await client.post(
        "/api/v1/tenants/",
        json={
            "name": "Audit Tenant",
            "slug": "audit-tenant",
            "description": "Tenant invitation audit checks",
        },
        headers=owner_headers,
    )
    assert tenant_response.status_code == 201, tenant_response.text
    tenant = tenant_response.json()

    invite_response = await client.post(
        f"/api/v1/tenants/{tenant['id']}/invitations",
        json={
            "email": "tenant_invitee_audit@example.com",
            "role": "member",
        },
        headers=owner_headers,
    )
    assert invite_response.status_code == 201, invite_response.text

    my_invites_response = await client.get(
        "/api/v1/tenants/invitations/me?status=pending",
        headers=invitee_headers,
    )
    assert my_invites_response.status_code == 200, my_invites_response.text
    pending_items = my_invites_response.json()["items"]
    assert len(pending_items) == 1
    pending_invitation = pending_items[0]
    assert pending_invitation["tenant_name"] == "Audit Tenant"
    assert pending_invitation["tenant_slug"] == "audit-tenant"
    assert pending_invitation["status"] == "pending"
    assert pending_invitation["decided_at"] is None
    assert pending_invitation["token"]

    decline_response = await client.post(
        "/api/v1/tenants/invitations/decline",
        json={"token": pending_invitation["token"]},
        headers=invitee_headers,
    )
    assert decline_response.status_code == 200, decline_response.text
    declined_invitation = decline_response.json()
    assert declined_invitation["status"] == "declined"
    assert declined_invitation["decided_at"] is not None

    history_response = await client.get(
        f"/api/v1/tenants/{tenant['id']}/invitations?status=declined",
        headers=owner_headers,
    )
    assert history_response.status_code == 200, history_response.text
    history_items = history_response.json()["items"]
    assert len(history_items) == 1
    assert history_items[0]["status"] == "declined"
    assert history_items[0]["decided_at"] is not None
