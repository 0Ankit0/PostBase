from fastapi import APIRouter, Depends, Query

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import FacadeStatusResponse
from src.postbase.capabilities.storage.contracts import SignedUrlResponse, StorageFileResponse, StorageUploadRequest
from src.postbase.capabilities.storage.dependencies import get_access_context, get_storage_facade, get_storage_provider
from src.postbase.capabilities.storage.service import StorageFacade

router = APIRouter(prefix="/storage", tags=["postbase-storage"])


@router.post("/files", response_model=StorageFileResponse)
async def upload_file(
    payload: StorageUploadRequest,
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> StorageFileResponse:
    return await provider.upload_file(context, payload)


@router.get("/files", response_model=PaginatedResponse[StorageFileResponse])
async def list_files(
    bucket_key: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> PaginatedResponse[StorageFileResponse]:
    return await provider.list_files(context, bucket_key, skip=skip, limit=limit)


@router.get("/files/{file_id}/signed-url", response_model=SignedUrlResponse)
async def get_signed_url(
    file_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> SignedUrlResponse:
    return await provider.signed_url(context, file_id)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> None:
    await provider.delete_file(context, file_id)


@router.get("/status", response_model=FacadeStatusResponse)
async def storage_status(
    context=Depends(get_access_context),
    facade: StorageFacade = Depends(get_storage_facade),
) -> FacadeStatusResponse:
    return await facade.status(context)
