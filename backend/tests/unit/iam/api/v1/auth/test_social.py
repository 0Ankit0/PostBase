import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import UserFactory


class _FakeResponse:
    def __init__(self, payload, *, json_error: Exception | None = None):
        self._payload = payload
        self._json_error = json_error

    def raise_for_status(self) -> None:
        return None

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


class TestSocialAuth:
    @pytest.mark.asyncio
    async def test_social_email_fallback_records_diagnostics_on_parse_error(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = UserFactory.build(
            username="social_user",
            email="social_user@example.com",
            hashed_password=None,
            social_provider="github",
            social_id="github-1",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        from src.apps.iam.api.v1.auth import social as social_module

        monkeypatch.setattr(social_module, "_assert_provider_enabled", lambda provider: None)
        monkeypatch.setattr(social_module.security, "verify_oauth_state", lambda state, provider: True)
        monkeypatch.setattr(social_module, "get_provider_credentials", lambda provider: ("client-id", "client-secret"))
        monkeypatch.setattr(social_module, "get_callback_url", lambda provider: "http://test/callback")
        monkeypatch.setattr(social_module, "extract_user_info", lambda provider, user_info: ("github-1", user_info.get("email"), "Social User"))
        monkeypatch.setattr(social_module, "find_or_create_social_user", AsyncMock(return_value=user))
        monkeypatch.setattr(social_module, "revoke_tokens_for_ip", AsyncMock())

        mock_record_security_error = AsyncMock()
        monkeypatch.setattr(social_module, "record_security_error_event", mock_record_security_error)

        responses = [
            _FakeResponse({"access_token": "provider-token"}),
            _FakeResponse({"id": "github-1", "login": "social_user"}),
            _FakeResponse(
                payload=None,
                json_error=json.JSONDecodeError("bad json", "x", 0),
            ),
        ]

        async def fake_retry_async(call):
            return responses.pop(0)

        class _FakeAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return responses.pop(0)

            async def get(self, *args, **kwargs):
                return responses.pop(0)

        monkeypatch.setattr(social_module, "retry_async", fake_retry_async)
        monkeypatch.setattr(social_module.httpx, "AsyncClient", _FakeAsyncClient)

        response = await client.get("/api/v1/auth/social/github/callback?code=test-code&state=test-state")

        assert response.status_code == 400
        assert "Could not retrieve email" in response.json()["detail"]
        mock_record_security_error.assert_awaited_once()
        assert (
            mock_record_security_error.await_args.kwargs["event_code"]
            == "auth.social_email_fallback_failed"
        )
