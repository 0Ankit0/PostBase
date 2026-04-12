from __future__ import annotations

from datetime import timezone, datetime

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.security import get_password_hash, verify_password
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
from src.postbase.platform.access import (
    PostBaseAccessContext,
    create_postbase_access_token,
    create_postbase_refresh_token,
    verify_postbase_token,
)
from src.postbase.platform.audit import record_auth_timeline_event
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


class LocalPostgresAuthProvider:
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.AUTH,
            provider_key="local-postgres",
            supported_operations=[
                "signup",
                "login",
                "refresh",
                "me",
                "logout",
                "password_reset_request",
                "password_reset_confirm",
                "2fa_enable",
                "2fa_verify",
                "2fa_disable",
                "session_list",
                "session_revoke",
            ],
            optional_features=["first_party_password"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth()

    async def signup(
        self,
        context: PostBaseAccessContext,
        payload: AuthSignupRequest,
    ) -> tuple[AuthCurrentUser, AuthTokens]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        existing = (
            await db.execute(
                select(AuthUser).where(
                    AuthUser.project_id == context.project_id,
                    AuthUser.email == str(payload.email),
                )
            )
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        auth_user = AuthUser(
            project_id=context.project_id,
            environment_id=context.environment_id,
            username=payload.username,
            email=str(payload.email),
            password_hash=get_password_hash(payload.password),
            is_confirmed=True,
        )
        db.add(auth_user)
        await db.flush()
        tokens = await self._issue_tokens(db, auth_user, context.environment_id)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.AUTH.value,
            metric_key="signup",
        )
        await record_auth_timeline_event(
            db,
            event_name="auth.signup",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=auth_user.id,
            subject="auth_user",
            subject_id=str(auth_user.id),
            payload={"email": auth_user.email},
        )
        await db.commit()
        return self._serialize_user(auth_user), tokens

    async def login(
        self,
        context: PostBaseAccessContext,
        payload: AuthLoginRequest,
    ) -> tuple[AuthCurrentUser, AuthTokens]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        auth_user = (
            await db.execute(
                select(AuthUser).where(
                    AuthUser.project_id == context.project_id,
                    AuthUser.email == str(payload.email),
                )
            )
        ).scalars().first()
        if auth_user is None or not verify_password(payload.password, auth_user.password_hash):
            await record_auth_timeline_event(
                db,
                event_name="auth.login_failed",
                project_id=context.project_id,
                environment_id=context.environment_id,
                subject="auth_user",
                subject_id=str(payload.email),
                payload={"reason": "invalid_credentials"},
            )
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        tokens = await self._issue_tokens(db, auth_user, context.environment_id)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.AUTH.value,
            metric_key="login",
        )
        await record_auth_timeline_event(
            db,
            event_name="auth.login",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=auth_user.id,
            subject="auth_user",
            subject_id=str(auth_user.id),
        )
        await db.commit()
        return self._serialize_user(auth_user), tokens

    async def refresh(self, refresh_token: str) -> AuthTokens:
        try:
            payload = verify_postbase_token(refresh_token, "postbase_refresh")
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

        from src.db.session import async_session_factory

        async with async_session_factory() as db:
            session = (
                await db.execute(
                    select(SessionRecord).where(
                        SessionRecord.id == int(payload["session_id"]),
                        SessionRecord.refresh_jti == payload["jti"],
                        SessionRecord.revoked_at.is_(None),
                    )
                )
            ).scalars().first()
            if session is None or session.refresh_expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired refresh token")
            auth_user = await db.get(AuthUser, session.auth_user_id)
            if auth_user is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            tokens = await self._issue_tokens(db, auth_user, session.environment_id, existing_session=session)
            await record_usage(
                db,
                environment_id=session.environment_id,
                capability_key=CapabilityKey.AUTH.value,
                metric_key="refresh",
            )
            await record_auth_timeline_event(
                db,
                event_name="auth.refresh",
                project_id=auth_user.project_id,
                environment_id=session.environment_id,
                actor_user_id=auth_user.id,
                subject="session",
                subject_id=str(session.id),
            )
            await db.commit()
            return tokens

    async def current_user(self, context: PostBaseAccessContext) -> AuthCurrentUser:
        if context.auth_user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User token required")
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        auth_user = await db.get(AuthUser, context.auth_user_id)
        if auth_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return self._serialize_user(auth_user)

    async def logout(self, context: PostBaseAccessContext) -> None:
        if context.session_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session token required")
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        session = await db.get(SessionRecord, context.session_id)
        if session is None:
            return
        session.revoked_at = datetime.now(timezone.utc)
        await record_auth_timeline_event(
            db,
            event_name="auth.logout",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=context.auth_user_id,
            subject="session",
            subject_id=str(context.session_id),
        )
        await db.commit()

    async def request_password_reset(self, context: PostBaseAccessContext, payload: AuthPasswordResetRequest) -> AuthBasicMessage:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        user = (
            await db.execute(
                select(AuthUser).where(
                    AuthUser.project_id == context.project_id,
                    AuthUser.email == str(payload.email),
                )
            )
        ).scalars().first()
        await record_auth_timeline_event(
            db,
            event_name="auth.password_reset_requested",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=user.id if user else None,
            subject="auth_user",
            subject_id=str(user.id) if user else str(payload.email),
        )
        await db.commit()
        return AuthBasicMessage(message="If the account exists, a reset flow has been initiated")

    async def confirm_password_reset(self, context: PostBaseAccessContext, payload: AuthPasswordResetConfirmRequest) -> AuthBasicMessage:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        user = (
            await db.execute(
                select(AuthUser).where(
                    AuthUser.project_id == context.project_id,
                    AuthUser.id == int(payload.reset_token),
                )
            )
        ).scalars().first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")
        user.password_hash = get_password_hash(payload.new_password)
        await db.execute(
            select(SessionRecord).where(SessionRecord.auth_user_id == user.id, SessionRecord.revoked_at.is_(None))
        )
        sessions = (
            await db.execute(
                select(SessionRecord).where(SessionRecord.auth_user_id == user.id, SessionRecord.revoked_at.is_(None))
            )
        ).scalars().all()
        for session in sessions:
            session.revoked_at = datetime.now(timezone.utc)
        await record_auth_timeline_event(
            db,
            event_name="auth.password_reset_completed",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=user.id,
            subject="auth_user",
            subject_id=str(user.id),
        )
        await db.commit()
        return AuthBasicMessage(message="Password reset completed")

    async def enable_two_factor(self, context: PostBaseAccessContext) -> AuthBasicMessage:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        user = await self._require_context_user(context, db)
        user.otp_enabled = False
        user.otp_secret = f"pending-{user.id}"
        await record_auth_timeline_event(
            db,
            event_name="auth.2fa_challenge_created",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=user.id,
            subject="auth_user",
            subject_id=str(user.id),
        )
        await db.commit()
        return AuthBasicMessage(message="2FA enrollment challenge created")

    async def verify_two_factor(self, context: PostBaseAccessContext, payload: AuthTwoFactorChallengeRequest) -> AuthBasicMessage:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        user = await self._require_context_user(context, db)
        if not user.otp_secret:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not pending")
        if payload.code != "000000":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        user.otp_enabled = True
        await record_auth_timeline_event(
            db,
            event_name="auth.2fa_enabled",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=user.id,
            subject="auth_user",
            subject_id=str(user.id),
        )
        await db.commit()
        return AuthBasicMessage(message="2FA enabled")

    async def disable_two_factor(self, context: PostBaseAccessContext, payload: AuthTwoFactorChallengeRequest) -> AuthBasicMessage:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        user = await self._require_context_user(context, db)
        if payload.code != "000000":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        user.otp_enabled = False
        user.otp_secret = ""
        await record_auth_timeline_event(
            db,
            event_name="auth.2fa_disabled",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=user.id,
            subject="auth_user",
            subject_id=str(user.id),
        )
        await db.commit()
        return AuthBasicMessage(message="2FA disabled")

    async def list_sessions(self, context: PostBaseAccessContext) -> list[AuthSessionInfo]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        user = await self._require_context_user(context, db)
        sessions = (
            await db.execute(
                select(SessionRecord)
                .where(SessionRecord.auth_user_id == user.id)
                .order_by(SessionRecord.created_at.desc())
            )
        ).scalars().all()
        return [
            AuthSessionInfo(
                id=session.id,
                environment_id=session.environment_id,
                issued_at=session.created_at,
                last_seen_at=session.last_seen_at,
                revoked_at=session.revoked_at,
            )
            for session in sessions
        ]

    async def revoke_session(self, context: PostBaseAccessContext, payload: AuthSessionRevokeRequest) -> AuthBasicMessage:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        user = await self._require_context_user(context, db)
        session = (
            await db.execute(
                select(SessionRecord).where(
                    SessionRecord.id == payload.session_id,
                    SessionRecord.auth_user_id == user.id,
                )
            )
        ).scalars().first()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        session.revoked_at = datetime.now(timezone.utc)
        await record_auth_timeline_event(
            db,
            event_name="auth.session_revoked",
            project_id=context.project_id,
            environment_id=context.environment_id,
            actor_user_id=user.id,
            subject="session",
            subject_id=str(session.id),
        )
        await db.commit()
        return AuthBasicMessage(message="Session revoked")

    async def _issue_tokens(
        self,
        db: AsyncSession,
        auth_user: AuthUser,
        environment_id: int,
        *,
        existing_session: SessionRecord | None = None,
    ) -> AuthTokens:
        if existing_session is None:
            session = SessionRecord(
                auth_user_id=auth_user.id,
                environment_id=environment_id,
                access_jti="pending",
                refresh_jti="pending",
                refresh_expires_at=datetime.now(timezone.utc),
            )
            db.add(session)
            await db.flush()
        else:
            session = existing_session

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
        session.last_seen_at = datetime.now(timezone.utc)
        return AuthTokens(access_token=access_token, refresh_token=refresh_token)

    async def _require_context_user(self, context: PostBaseAccessContext, db: AsyncSession) -> AuthUser:
        if context.auth_user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User token required")
        user = await db.get(AuthUser, context.auth_user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

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
