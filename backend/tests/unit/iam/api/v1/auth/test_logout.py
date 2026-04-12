import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.core import security
from tests.factories import UserFactory


class TestLogout:
    """Test logout endpoint."""
    
    @pytest.mark.asyncio
    async def test_logout_requires_auth(self, client: AsyncClient):
        """Test logout requires authentication."""
        response = await client.post("/api/v1/auth/logout/")
        
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_logs_revocation_failure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        hashed_pw = security.get_password_hash("TestPass123")
        user = UserFactory.build(
            username="logoutfailuser",
            email="logout-failure@example.com",
            hashed_password=hashed_pw,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        login_response = await client.post(
            "/api/v1/auth/login/?set_cookie=false",
            json={"username": "logoutfailuser", "password": "TestPass123"},
        )
        token = login_response.json()["access"]

        with patch("src.apps.iam.api.v1.auth.login.jwt.decode", side_effect=RuntimeError("decode failed")):
            with patch(
                "src.apps.iam.api.v1.auth.login.record_security_error_event",
                new_callable=AsyncMock,
            ) as mock_record_security_error:
                response = await client.post(
                    "/api/v1/auth/logout/",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 200
        mock_record_security_error.assert_awaited_once()
        assert mock_record_security_error.await_args.kwargs["event_code"] == "auth.logout_revocation_failed"
