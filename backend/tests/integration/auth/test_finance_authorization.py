import base64
import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.finance.models.payment import PaymentProvider, PaymentStatus, PaymentTransaction
from src.apps.iam.models.user import User
from src.apps.iam.utils.hashid import encode_id


def _esewa_sig(message: str, secret: str = "8gBm/:&EnhH.1/q") -> str:
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def _esewa_callback_data(transaction_uuid: str, total_amount: int = 100) -> str:
    signed_field_names = "transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names"
    fields_values = {
        "transaction_code": "TXNCODE123",
        "status": "COMPLETE",
        "total_amount": str(total_amount),
        "transaction_uuid": transaction_uuid,
        "product_code": "EPAYTEST",
        "signed_field_names": signed_field_names,
    }
    message = ",".join(f"{field}={fields_values[field]}" for field in signed_field_names.split(","))
    fields_values["signature"] = _esewa_sig(message)
    return base64.b64encode(json.dumps(fields_values).encode()).decode()


async def _signup_and_get_token(client: AsyncClient, username: str, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": username,
            "email": email,
            "password": "FinanceAuth123!",
            "confirm_password": "FinanceAuth123!",
        },
    )
    assert response.status_code == 200
    return response.json()["access"]


@pytest.mark.asyncio
async def test_private_payment_routes_require_auth(client: AsyncClient):
    body = {
        "provider": "khalti",
        "amount": 1000,
        "purchase_order_id": "AUTH-REQ-001",
        "purchase_order_name": "Auth Required",
        "return_url": "http://localhost:3000/callback",
    }

    initiate = await client.post("/api/v1/payments/initiate/", json=body)
    verify = await client.post("/api/v1/payments/verify/", json={"provider": "khalti", "pidx": "pidx"})
    providers = await client.get("/api/v1/payments/providers/")
    listing = await client.get("/api/v1/payments/")
    detail = await client.get("/api/v1/payments/abc123/")

    assert initiate.status_code == 401
    assert verify.status_code == 401
    assert providers.status_code == 401
    assert listing.status_code == 401
    assert detail.status_code == 401


@pytest.mark.asyncio
async def test_user_cannot_access_or_verify_another_users_transaction(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner_token = await _signup_and_get_token(client, "finance_owner", "finance_owner@example.com")
    attacker_token = await _signup_and_get_token(client, "finance_attacker", "finance_attacker@example.com")
    owner = (
        await db_session.execute(select(User).where(User.username == "finance_owner"))
    ).scalars().first()
    assert owner is not None

    tx = PaymentTransaction(
        provider=PaymentProvider.ESEWA,
        amount=100,
        purchase_order_id="OWNER-ORDER-001",
        purchase_order_name="Owner Payment",
        return_url="http://localhost:3000/callback",
        website_url="http://localhost:3000",
        status=PaymentStatus.INITIATED,
        provider_pidx="owner-uuid-123",
        user_id=owner.id,
    )
    db_session.add(tx)
    await db_session.commit()
    await db_session.refresh(tx)

    attacker_headers = {"Authorization": f"Bearer {attacker_token}"}
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    list_resp = await client.get("/api/v1/payments/", headers=attacker_headers)
    assert list_resp.status_code == 200
    assert all(row["id"] != str(tx.id) for row in list_resp.json())

    detail_resp = await client.get(f"/api/v1/payments/{encode_id(tx.id)}/", headers=attacker_headers)
    assert detail_resp.status_code == 403

    verify_resp = await client.post(
        "/api/v1/payments/verify/",
        json={"provider": "esewa", "data": _esewa_callback_data("owner-uuid-123", total_amount=100)},
        headers=attacker_headers,
    )
    assert verify_resp.status_code == 403

    owner_detail_resp = await client.get(f"/api/v1/payments/{encode_id(tx.id)}/", headers=owner_headers)
    assert owner_detail_resp.status_code == 200
