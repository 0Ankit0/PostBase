from __future__ import annotations

from fastapi import APIRouter, Depends

from src.postbase.capabilities.contracts import CAPABILITY_ERROR_RESPONSES, FacadeStatusResponse
from src.postbase.capabilities.auth.contracts import (
    AuthCurrentUser,
    AuthLoginRequest,
    AuthRefreshRequest,
    AuthSessionResponse,
    AuthSignupRequest,
    AuthTokens,
)
from src.postbase.capabilities.auth.dependencies import (
    get_access_context,
    get_auth_facade,
    get_auth_provider,
)
from src.postbase.capabilities.auth.service import AuthFacade

router = APIRouter(prefix="/auth", tags=["postbase-auth"])


@router.post("/users", response_model=AuthSessionResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def signup(
    payload: AuthSignupRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthSessionResponse:
    user, tokens = await provider.signup(context, payload)
    return AuthSessionResponse(user=user, tokens=tokens)


@router.post("/sessions", response_model=AuthSessionResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def login(
    payload: AuthLoginRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthSessionResponse:
    user, tokens = await provider.login(context, payload)
    return AuthSessionResponse(user=user, tokens=tokens)


@router.post("/sessions/refresh", response_model=AuthTokens, responses=CAPABILITY_ERROR_RESPONSES)
async def refresh(
    payload: AuthRefreshRequest,
    provider=Depends(get_auth_provider),
) -> AuthTokens:
    return await provider.refresh(payload.refresh_token)


@router.get("/me", response_model=AuthCurrentUser, responses=CAPABILITY_ERROR_RESPONSES)
async def me(
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthCurrentUser:
    return await provider.current_user(context)


@router.post("/logout", status_code=204, responses=CAPABILITY_ERROR_RESPONSES)
async def logout(
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> None:
    await provider.logout(context)


@router.get("/status", response_model=FacadeStatusResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def auth_status(
    context=Depends(get_access_context),
    facade: AuthFacade = Depends(get_auth_facade),
) -> FacadeStatusResponse:
    return await facade.status(context)
