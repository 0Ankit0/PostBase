from fastapi import Depends

from src.postbase.capabilities.auth.dependencies import get_access_context
from src.postbase.capabilities.events.service import EventsFacade


def get_events_facade() -> EventsFacade:
    return EventsFacade()


async def get_events_provider(
    context=Depends(get_access_context),
    facade: EventsFacade = Depends(get_events_facade),
):
    return await facade.resolve_provider(context)


__all__ = ["get_access_context", "get_events_facade", "get_events_provider"]
