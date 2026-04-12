from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import CAPABILITY_ERROR_RESPONSES, FacadeStatusResponse
from src.postbase.capabilities.storage.contracts import (
    FileMetadataPatchRequest,
    RetentionExecutionResponse,
    RetentionRuleCreate,
    RetentionRuleResponse,
    SignedUrlIssueRequest,
    SignedUrlLifecycleResponse,
    SignedUrlResponse,
    StorageFileResponse,
    StorageLifecycleResponse,
    StoragePolicyRead,
    StorageUploadInitRequest,
    StorageUploadRequest,
)
from src.postbase.capabilities.storage.dependencies import get_access_context, get_storage_facade, get_storage_provider
from src.postbase.capabilities.storage.service import StorageFacade

router = APIRouter(prefix="/storage", tags=["postbase-storage"])


@router.post("/uploads/init", response_model=SignedUrlResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def init_upload(payload: StorageUploadInitRequest, context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> SignedUrlResponse:
    return await provider.init_upload(context, payload)


@router.post("/files", response_model=StorageFileResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def upload_file(payload: StorageUploadRequest, context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> StorageFileResponse:
    return await provider.upload_file(context, payload)


@router.get("/files", response_model=PaginatedResponse[StorageFileResponse], responses=CAPABILITY_ERROR_RESPONSES)
async def list_files(
    bucket_key: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> PaginatedResponse[StorageFileResponse]:
    return await provider.list_files(context, bucket_key, skip=skip, limit=limit)


@router.get("/files/{file_id}/signed-url", response_model=SignedUrlResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def get_signed_url(file_id: int, context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> SignedUrlResponse:
    return await provider.signed_url(context, file_id)


@router.post("/files/{file_id}/signed-urls", response_model=SignedUrlLifecycleResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def issue_signed_url(
    file_id: int,
    payload: SignedUrlIssueRequest,
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> SignedUrlLifecycleResponse:
    return await provider.issue_signed_url(context, file_id, payload)


@router.post("/signed-urls/{grant_id}/refresh", response_model=SignedUrlLifecycleResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def refresh_signed_url(
    grant_id: int,
    payload: SignedUrlIssueRequest,
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> SignedUrlLifecycleResponse:
    return await provider.refresh_signed_url(context, grant_id, payload)


@router.delete("/signed-urls/{grant_id}", status_code=204, responses=CAPABILITY_ERROR_RESPONSES)
async def revoke_signed_url(grant_id: int, context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> None:
    await provider.revoke_signed_url(context, grant_id)


@router.get("/files/{file_id}/metadata", response_model=StorageFileResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def read_file_metadata(file_id: int, context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> StorageFileResponse:
    return await provider.read_metadata(context, file_id)


@router.patch("/files/{file_id}/metadata", response_model=StorageFileResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def write_file_metadata(
    file_id: int,
    payload: FileMetadataPatchRequest,
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> StorageFileResponse:
    return await provider.write_metadata(context, file_id, payload)


@router.get("/files/{file_id}/lifecycle", response_model=StorageLifecycleResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def file_lifecycle_state(file_id: int, context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> StorageLifecycleResponse:
    return await provider.lifecycle_state(context, file_id)


@router.get("/policy", response_model=StoragePolicyRead, responses=CAPABILITY_ERROR_RESPONSES)
async def storage_policy(context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> StoragePolicyRead:
    return await provider.policy(context)


@router.post("/retention/rules", response_model=RetentionRuleResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def create_retention_rule(
    payload: RetentionRuleCreate,
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> RetentionRuleResponse:
    return await provider.create_retention_rule(context, payload)


@router.get("/retention/rules", response_model=list[RetentionRuleResponse], responses=CAPABILITY_ERROR_RESPONSES)
async def list_retention_rules(context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> list[RetentionRuleResponse]:
    return await provider.list_retention_rules(context)


@router.post("/retention/run", response_model=RetentionExecutionResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def run_retention(
    context=Depends(get_access_context),
    provider=Depends(get_storage_provider),
) -> RetentionExecutionResponse:
    return await provider.run_retention(context, now=datetime.now(timezone.utc))


@router.delete("/files/{file_id}", status_code=204, responses=CAPABILITY_ERROR_RESPONSES)
async def delete_file(file_id: int, context=Depends(get_access_context), provider=Depends(get_storage_provider)) -> None:
    await provider.delete_file(context, file_id)


@router.get("/status", response_model=FacadeStatusResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def storage_status(
    context=Depends(get_access_context),
    facade: StorageFacade = Depends(get_storage_facade),
) -> FacadeStatusResponse:
    return await facade.status(context)
