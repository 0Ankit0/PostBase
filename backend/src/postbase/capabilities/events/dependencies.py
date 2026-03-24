from fastapi import Depends

from src.postbase.capabilities.auth.dependencies import get_access_context
from src.postbase.capabilities.events.service import EventsFacade


async def get_events_provider(context=Depends(get_access_context)):
    return await EventsFacade().resolve_provider(context)


__all__ = ["get_access_context", "get_events_provider"]
