import pytest
from sqlmodel import select

from src.apps.iam.models.user import User


@pytest.mark.asyncio
async def test_observability_auth_timeline_returns_normalized_auth_events(client, db_session):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": "audit_admin",
            "email": "audit-admin@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text

    user = (await db_session.execute(select(User).where(User.email == "audit-admin@example.com"))).scalars().first()
    user.is_superuser = True
    await db_session.commit()

    login_response = await client.post(
        "/api/v1/auth/login/?set_cookie=false",
        json={"username": "audit-admin@example.com", "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200, login_response.text
    headers = {"Authorization": f"Bearer {login_response.json()['access']}"}

    await client.post("/api/v1/auth/otp/enable/", headers=headers)

    timeline_response = await client.get("/api/v1/observability/auth-timeline", headers=headers)
    assert timeline_response.status_code == 200, timeline_response.text
    payload = timeline_response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["event_name"].startswith("auth.")
