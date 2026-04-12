from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import PostBaseContractModel
from src.postbase.platform.contracts import ProviderAdapter


class StorageUploadRequest(PostBaseContractModel):
    filename: str
    content_base64: str
    content_type: str = "application/octet-stream"
    bucket_key: str = "default"
    namespace: str = "default"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class StorageFileResponse(PostBaseContractModel):
    id: int
    bucket_key: str
    path: str
    filename: str
    content_type: str
    size_bytes: int
    url: str
    metadata_json: dict[str, Any]


class SignedUrlResponse(PostBaseContractModel):
    file_id: int
    url: str


class StorageProvider(ProviderAdapter, Protocol):
    async def upload_file(self, context, payload: StorageUploadRequest) -> StorageFileResponse:
        ...

    async def list_files(
        self,
        context,
        bucket_key: str | None = None,
        *,
        skip: int,
        limit: int,
    ) -> PaginatedResponse[StorageFileResponse]:
        ...

    async def signed_url(self, context, file_id: int) -> SignedUrlResponse:
        ...

    async def delete_file(self, context, file_id: int) -> None:
        ...
