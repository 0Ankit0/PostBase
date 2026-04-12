from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import jwk, jwt
from jose.utils import base64url_decode
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.security import get_password_hash
from src.postbase.capabilities.auth.contracts import (
    AuthBasicMessage,
    AuthCurrentUser,
    AuthLoginRequest,
    AuthPasswordResetConfirmRequest,
    AuthPasswordResetRequest,
    AuthSessionInfo,
    AuthSessionRevokeRequest,
    AuthSignupRequest,
    AuthTokens,
    AuthTwoFactorChallengeRequest,
)
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import AuthUser, SessionRecord
from src.postbase.platform.access import PostBaseAccessContext, create_postbase_access_token, create_postbase_refresh_token
from src.postbase.platform.audit import record_auth_timeline_event
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth


class OIDCStrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer_url: AnyHttpUrl
    client_id: str = Field(min_length=3)
    expected_audience: str = Field(min_length=3)
    expected_state: str = Field(min_length=8)
    expected_nonce: str = Field(min_length=8)
    leeway_seconds: int = Field(default=30, ge=0, le=120)
    discovery_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    jwks_ttl_seconds: int = Field(default=900, ge=60, le=86400)


class OIDCCertifiedAuthProvider:
    _discovery_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
    _jwks_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}

    def __init__(self) -> None:
        self._binding_config: dict[str, Any] = {}

    def configure_binding(self, binding) -> None:
        self._binding_config = binding.config

    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.AUTH,
            provider_key="oidc-certified",
            adapter_version="1.0.0",
            supported_operations=["login", "refresh", "me", "logout", "session_list", "session_revoke"],
            required_secret_kinds=[],
            optional_features=["oidc_discovery", "jwks_cache", "nonce_validation", "state_validation"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth()

    async def signup(self, context: PostBaseAccessContext, payload: AuthSignupRequest) -> tuple[AuthCurrentUser, AuthTokens]:
        del context, payload
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC provider does not support direct signup")

    async def login(self, context: PostBaseAccessContext, payload: AuthLoginRequest) -> tuple[AuthCurrentUser, AuthTokens]:
        config = OIDCStrictConfig.model_validate(self._binding_config)
        claims = await self._verify_id_token(payload.password, config)
        if claims.get("email") and str(claims.get("email")).lower() != str(payload.email).lower():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC subject mismatch")
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        email = str(claims.get("email") or payload.email)
        sub = str(claims.get("sub") or email)
        user = (
            await db.execute(
                select(AuthUser).where(AuthUser.project_id == context.project_id, AuthUser.email == email)
            )
        ).scalars().first()
        if user is None:
            user = AuthUser(
                project_id=context.project_id,
                environment_id=context.environment_id,
                username=f"oidc-{sub[:24]}",
                email=email,
                password_hash=get_password_hash(sub),
                is_confirmed=True,
            )
            db.add(user)
            await db.flush()
        tokens = await self._issue_tokens(db, user, context.environment_id)
        await record_auth_timeline_event(
            db,
            event_name="auth.oidc_login",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=user.id,
            subject="auth_user",
            subject_id=str(user.id),
            payload={"issuer": str(config.issuer_url)},
        )
        await db.commit()
        return self._serialize_user(user), tokens

    async def refresh(self, refresh_token: str) -> AuthTokens:
        from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider

        return await LocalPostgresAuthProvider().refresh(refresh_token)

    async def current_user(self, context: PostBaseAccessContext) -> AuthCurrentUser:
        from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider

        return await LocalPostgresAuthProvider().current_user(context)

    async def logout(self, context: PostBaseAccessContext) -> None:
        from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider

        await LocalPostgresAuthProvider().logout(context)

    async def request_password_reset(self, context: PostBaseAccessContext, payload: AuthPasswordResetRequest) -> AuthBasicMessage:
        del context, payload
        return AuthBasicMessage(message="Password reset is managed by your OIDC identity provider")

    async def confirm_password_reset(self, context: PostBaseAccessContext, payload: AuthPasswordResetConfirmRequest) -> AuthBasicMessage:
        del context, payload
        return AuthBasicMessage(message="Password reset confirmation is managed by your OIDC identity provider")

    async def enable_two_factor(self, context: PostBaseAccessContext) -> AuthBasicMessage:
        del context
        return AuthBasicMessage(message="2FA is managed by your OIDC identity provider")

    async def disable_two_factor(self, context: PostBaseAccessContext, payload: AuthTwoFactorChallengeRequest) -> AuthBasicMessage:
        del context, payload
        return AuthBasicMessage(message="2FA is managed by your OIDC identity provider")

    async def verify_two_factor(self, context: PostBaseAccessContext, payload: AuthTwoFactorChallengeRequest) -> AuthBasicMessage:
        del context, payload
        return AuthBasicMessage(message="2FA is managed by your OIDC identity provider")

    async def list_sessions(self, context: PostBaseAccessContext) -> list[AuthSessionInfo]:
        from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider

        return await LocalPostgresAuthProvider().list_sessions(context)

    async def revoke_session(self, context: PostBaseAccessContext, payload: AuthSessionRevokeRequest) -> AuthBasicMessage:
        from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider

        return await LocalPostgresAuthProvider().revoke_session(context, payload)

    async def _verify_id_token(self, id_token: str, config: OIDCStrictConfig) -> dict[str, Any]:
        discovery = await self._discover(config)
        jwks = await self._get_jwks(discovery["jwks_uri"], ttl_seconds=config.jwks_ttl_seconds)
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown signing key")

        public_key = jwk.construct(key_data)
        message, encoded_sig = id_token.rsplit(".", 1)
        decoded_sig = base64url_decode(encoded_sig.encode("utf-8"))
        if not public_key.verify(message.encode("utf-8"), decoded_sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

        claims = jwt.get_unverified_claims(id_token)
        now = datetime.now(timezone.utc).timestamp()
        leeway = config.leeway_seconds
        if claims.get("iss") != str(config.issuer_url).rstrip("/"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected issuer")
        aud = claims.get("aud")
        aud_values = aud if isinstance(aud, list) else [aud]
        if config.expected_audience not in aud_values and config.client_id not in aud_values:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected audience")
        if claims.get("nonce") != config.expected_nonce:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid nonce")
        if claims.get("state") != config.expected_state:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid state")
        if float(claims.get("exp", 0)) < now - leeway:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired token")
        if float(claims.get("nbf", 0)) > now + leeway:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token not active")
        return claims

    async def _discover(self, config: OIDCStrictConfig) -> dict[str, Any]:
        issuer = str(config.issuer_url).rstrip("/")
        cached = self._discovery_cache.get(issuer)
        now = datetime.now(timezone.utc)
        if cached and cached[0] > now:
            return cached[1]
        url = f"{issuer}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        payload = response.json()
        self._discovery_cache[issuer] = (now + timedelta(seconds=config.discovery_ttl_seconds), payload)
        return payload

    async def _get_jwks(self, jwks_uri: str, *, ttl_seconds: int) -> dict[str, Any]:
        cached = self._jwks_cache.get(jwks_uri)
        now = datetime.now(timezone.utc)
        if cached and cached[0] > now:
            return cached[1]
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(jwks_uri)
            response.raise_for_status()
        payload = response.json()
        self._jwks_cache[jwks_uri] = (now + timedelta(seconds=ttl_seconds), payload)
        return payload

    async def _issue_tokens(self, db: AsyncSession, auth_user: AuthUser, environment_id: int) -> AuthTokens:
        session = SessionRecord(
            auth_user_id=auth_user.id,
            environment_id=environment_id,
            access_jti="pending",
            refresh_jti="pending",
            refresh_expires_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()
        access_token, access_jti = create_postbase_access_token(
            auth_user_id=auth_user.id,
            project_id=auth_user.project_id,
            environment_id=environment_id,
            session_id=session.id,
        )
        refresh_token, refresh_jti, refresh_expires_at = create_postbase_refresh_token(
            auth_user_id=auth_user.id,
            project_id=auth_user.project_id,
            environment_id=environment_id,
            session_id=session.id,
        )
        session.access_jti = access_jti
        session.refresh_jti = refresh_jti
        session.refresh_expires_at = refresh_expires_at
        return AuthTokens(access_token=access_token, refresh_token=refresh_token)

    def _serialize_user(self, auth_user: AuthUser) -> AuthCurrentUser:
        return AuthCurrentUser(
            id=auth_user.id,
            project_id=auth_user.project_id,
            environment_id=auth_user.environment_id,
            username=auth_user.username,
            email=auth_user.email,
            is_active=auth_user.is_active,
            two_factor_enabled=auth_user.otp_enabled,
        )
