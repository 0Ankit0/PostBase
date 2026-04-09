from fastapi import Depends

from src.postbase.capabilities.auth.dependencies import get_access_context
from src.postbase.capabilities.functions.service import FunctionsFacade


def get_functions_facade() -> FunctionsFacade:
    return FunctionsFacade()


async def get_functions_provider(
    context=Depends(get_access_context),
    facade: FunctionsFacade = Depends(get_functions_facade),
):
    return await facade.resolve_provider(context)


__all__ = ["get_access_context", "get_functions_facade", "get_functions_provider"]
