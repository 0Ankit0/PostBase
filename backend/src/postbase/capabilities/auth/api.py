from __future__ import annotations

from fastapi import APIRouter, Depends

from src.postbase.capabilities.contracts import CAPABILITY_ERROR_RESPONSES, FacadeStatusResponse
from src.postbase.capabilities.auth.contracts import (
    AuthBasicMessage,
    AuthCurrentUser,
    AuthLoginRequest,
    AuthPasswordResetConfirmRequest,
    AuthPasswordResetRequest,
    AuthRefreshRequest,
    AuthSessionInfo,
    AuthSessionResponse,
    AuthSessionRevokeRequest,
    AuthSignupRequest,
    AuthTokens,
    AuthTwoFactorChallengeRequest,
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


@router.post("/password/reset", response_model=AuthBasicMessage, responses=CAPABILITY_ERROR_RESPONSES)
async def request_password_reset(
    payload: AuthPasswordResetRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthBasicMessage:
    return await provider.request_password_reset(context, payload)


@router.post("/password/reset/confirm", response_model=AuthBasicMessage, responses=CAPABILITY_ERROR_RESPONSES)
async def confirm_password_reset(
    payload: AuthPasswordResetConfirmRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthBasicMessage:
    return await provider.confirm_password_reset(context, payload)


@router.post("/2fa/enable", response_model=AuthBasicMessage, responses=CAPABILITY_ERROR_RESPONSES)
async def enable_two_factor(
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthBasicMessage:
    return await provider.enable_two_factor(context)


@router.post("/2fa/verify", response_model=AuthBasicMessage, responses=CAPABILITY_ERROR_RESPONSES)
async def verify_two_factor(
    payload: AuthTwoFactorChallengeRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthBasicMessage:
    return await provider.verify_two_factor(context, payload)


@router.post("/2fa/disable", response_model=AuthBasicMessage, responses=CAPABILITY_ERROR_RESPONSES)
async def disable_two_factor(
    payload: AuthTwoFactorChallengeRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthBasicMessage:
    return await provider.disable_two_factor(context, payload)


@router.get("/sessions", response_model=list[AuthSessionInfo], responses=CAPABILITY_ERROR_RESPONSES)
async def list_sessions(
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> list[AuthSessionInfo]:
    return await provider.list_sessions(context)


@router.post("/sessions/revoke", response_model=AuthBasicMessage, responses=CAPABILITY_ERROR_RESPONSES)
async def revoke_session(
    payload: AuthSessionRevokeRequest,
    context=Depends(get_access_context),
    provider=Depends(get_auth_provider),
) -> AuthBasicMessage:
    return await provider.revoke_session(context, payload)
