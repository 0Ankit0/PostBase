from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import EmailStr, Field

from src.postbase.capabilities.contracts import PostBaseContractModel
from src.postbase.platform.contracts import ProviderAdapter


class AuthSignupRequest(PostBaseContractModel):
    username: str
    email: EmailStr
    password: str


class AuthLoginRequest(PostBaseContractModel):
    email: EmailStr
    password: str


class AuthRefreshRequest(PostBaseContractModel):
    refresh_token: str = Field(min_length=1)


class AuthPasswordResetRequest(PostBaseContractModel):
    email: EmailStr


class AuthPasswordResetConfirmRequest(PostBaseContractModel):
    reset_token: str = Field(min_length=1)
    new_password: str


class AuthTwoFactorChallengeRequest(PostBaseContractModel):
    code: str = Field(min_length=4, max_length=12)


class AuthSessionRevokeRequest(PostBaseContractModel):
    session_id: int


class AuthTokens(PostBaseContractModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthCurrentUser(PostBaseContractModel):
    id: int
    project_id: int
    environment_id: int
    username: str
    email: EmailStr
    is_active: bool
    two_factor_enabled: bool = False


class AuthSessionInfo(PostBaseContractModel):
    id: int
    environment_id: int
    issued_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None


class AuthSessionResponse(PostBaseContractModel):
    user: AuthCurrentUser
    tokens: AuthTokens


class AuthBasicMessage(PostBaseContractModel):
    message: str


class AuthProvider(ProviderAdapter, Protocol):
    async def signup(self, context, payload: AuthSignupRequest) -> tuple[AuthCurrentUser, AuthTokens]: ...

    async def login(self, context, payload: AuthLoginRequest) -> tuple[AuthCurrentUser, AuthTokens]: ...

    async def refresh(self, refresh_token: str) -> AuthTokens: ...

    async def current_user(self, context) -> AuthCurrentUser: ...

    async def logout(self, context) -> None: ...

    async def request_password_reset(self, context, payload: AuthPasswordResetRequest) -> AuthBasicMessage: ...

    async def confirm_password_reset(self, context, payload: AuthPasswordResetConfirmRequest) -> AuthBasicMessage: ...

    async def enable_two_factor(self, context) -> AuthBasicMessage: ...

    async def disable_two_factor(self, context, payload: AuthTwoFactorChallengeRequest) -> AuthBasicMessage: ...

    async def verify_two_factor(self, context, payload: AuthTwoFactorChallengeRequest) -> AuthBasicMessage: ...

    async def list_sessions(self, context) -> list[AuthSessionInfo]: ...

    async def revoke_session(self, context, payload: AuthSessionRevokeRequest) -> AuthBasicMessage: ...
