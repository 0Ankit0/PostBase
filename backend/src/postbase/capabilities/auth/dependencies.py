from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.iam.api.deps import get_db
from src.postbase.capabilities.auth.service import AuthFacade
from src.postbase.platform.access import (
    PostBaseAccessContext,
    resolve_access_context_from_token,
    resolve_api_key_context,
)

_bearer = HTTPBearer(auto_error=False)


async def get_access_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str | None = Header(default=None, alias="X-PostBase-Key"),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> PostBaseAccessContext:
    if credentials:
        context = await resolve_access_context_from_token(db, credentials.credentials)
        if context is not None:
            setattr(context, "db", db)
            return context

    if api_key:
        context = await resolve_api_key_context(db, api_key)
        if context is not None:
            setattr(context, "db", db)
            return context

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid PostBase access credentials",
    )


async def get_auth_provider(
    context: PostBaseAccessContext = Depends(get_access_context),
):
    return await AuthFacade().resolve_provider(context)
