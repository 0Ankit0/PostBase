from fastapi import Depends

from src.postbase.capabilities.auth.dependencies import get_access_context
from src.postbase.capabilities.functions.service import FunctionsFacade


async def get_functions_provider(context=Depends(get_access_context)):
    return await FunctionsFacade().resolve_provider(context)


__all__ = ["get_access_context", "get_functions_provider"]
