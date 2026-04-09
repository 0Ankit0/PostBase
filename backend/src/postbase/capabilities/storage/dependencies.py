from fastapi import Depends

from src.postbase.capabilities.auth.dependencies import get_access_context
from src.postbase.capabilities.storage.service import StorageFacade


def get_storage_facade() -> StorageFacade:
    return StorageFacade()


async def get_storage_provider(
    context=Depends(get_access_context),
    facade: StorageFacade = Depends(get_storage_facade),
):
    return await facade.resolve_provider(context)


__all__ = ["get_access_context", "get_storage_facade", "get_storage_provider"]
