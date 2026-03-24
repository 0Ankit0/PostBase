from __future__ import annotations

from fastapi import APIRouter, Depends

from src.postbase.capabilities.auth.contracts import (
    AuthCurrentUser,
    AuthLoginRequest,
    AuthSignupRequest,
    AuthTokens,
)
from src.postbase.capabilities.auth.dependencies import get_access_context, get_auth_provider

router = APIRouter(prefix="/auth", tags=["postbase-auth"])


@router.post("/users")
async def signup(
    payload: AuthSignupRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> dict:
    user, tokens = await provider.signup(context, payload)
    return {"user": user.model_dump(), "tokens": tokens.model_dump()}


@router.post("/sessions")
async def login(
    payload: AuthLoginRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> dict:
    user, tokens = await provider.login(context, payload)
    return {"user": user.model_dump(), "tokens": tokens.model_dump()}


@router.post("/sessions/refresh", response_model=AuthTokens)
async def refresh(
    payload: dict,
    provider=Depends(get_auth_provider),
) -> AuthTokens:
    return await provider.refresh(payload["refresh_token"])


@router.get("/me", response_model=AuthCurrentUser)
async def me(
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthCurrentUser:
    return await provider.current_user(context)


@router.post("/logout", status_code=204)
async def logout(
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> None:
    await provider.logout(context)
