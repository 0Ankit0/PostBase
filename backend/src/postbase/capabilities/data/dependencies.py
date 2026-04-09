from fastapi import Depends

from src.postbase.capabilities.auth.dependencies import get_access_context
from src.postbase.capabilities.data.service import DataFacade


def get_data_facade() -> DataFacade:
    return DataFacade()


async def get_data_provider(
    context=Depends(get_access_context),
    facade: DataFacade = Depends(get_data_facade),
):
    return await facade.resolve_provider(context)


__all__ = ["get_access_context", "get_data_facade", "get_data_provider"]
