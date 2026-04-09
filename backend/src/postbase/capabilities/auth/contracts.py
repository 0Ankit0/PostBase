from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, EmailStr, Field

from src.postbase.platform.contracts import ProviderAdapter


class AuthSignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthCurrentUser(BaseModel):
    id: int
    project_id: int
    environment_id: int
    username: str
    email: EmailStr
    is_active: bool


class AuthSessionResponse(BaseModel):
    user: AuthCurrentUser
    tokens: AuthTokens


class AuthProvider(ProviderAdapter, Protocol):
    async def signup(self, context, payload: AuthSignupRequest) -> tuple[AuthCurrentUser, AuthTokens]:
        ...

    async def login(self, context, payload: AuthLoginRequest) -> tuple[AuthCurrentUser, AuthTokens]:
        ...

    async def refresh(self, refresh_token: str) -> AuthTokens:
        ...

    async def current_user(self, context) -> AuthCurrentUser:
        ...

    async def logout(self, context) -> None:
        ...
