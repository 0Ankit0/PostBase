from fastapi import Depends

from src.postbase.capabilities.auth.dependencies import get_access_context
from src.postbase.capabilities.data.service import DataFacade


async def get_data_provider(context=Depends(get_access_context)):
    return await DataFacade().resolve_provider(context)


__all__ = ["get_access_context", "get_data_provider"]
