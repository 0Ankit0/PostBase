from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

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


class StorageUploadInitRequest(PostBaseContractModel):
    filename: str
    content_type: str = "application/octet-stream"
    bucket_key: str = "default"
    namespace: str = "default"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    expires_in_seconds: int = Field(default=900, ge=60, le=86_400)


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
    expires_at: datetime | None = None
    grant_id: int | None = None
    token: str | None = None
    access_mode: Literal["read", "write"] = "read"


class SignedUrlIssueRequest(PostBaseContractModel):
    access_mode: Literal["read", "write"] = "read"
    expires_in_seconds: int = Field(default=900, ge=60, le=86_400)


class SignedUrlLifecycleResponse(PostBaseContractModel):
    grant_id: int
    file_id: int
    access_mode: str
    token: str
    url: str
    expires_at: datetime
    revoked_at: datetime | None


class FileMetadataPatchRequest(PostBaseContractModel):
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class StorageLifecycleResponse(PostBaseContractModel):
    file_id: int
    lifecycle_state: str
    detail: str


class StoragePolicyRead(PostBaseContractModel):
    capability: str = "storage"
    mode: str = "signed-url"
    max_signed_url_ttl_seconds: int
    retention_rules: list[dict[str, Any]] = Field(default_factory=list)


class RetentionRuleCreate(PostBaseContractModel):
    bucket_key: str = "default"
    namespace: str = "default"
    max_age_days: int = Field(ge=1, le=3650)
    sweep_interval_minutes: int = Field(default=60, ge=1, le=1440)
    enabled: bool = True


class RetentionRuleResponse(PostBaseContractModel):
    id: int
    bucket_key: str
    namespace: str
    max_age_days: int
    sweep_interval_minutes: int
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None


class RetentionExecutionResponse(PostBaseContractModel):
    scanned_files: int
    deleted_files: int
    updated_rules: int


class StorageProvider(ProviderAdapter, Protocol):
    async def upload_file(self, context, payload: StorageUploadRequest) -> StorageFileResponse:
        ...

    async def init_upload(self, context, payload: StorageUploadInitRequest) -> SignedUrlResponse:
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

    async def issue_signed_url(self, context, file_id: int, payload: SignedUrlIssueRequest) -> SignedUrlLifecycleResponse:
        ...

    async def refresh_signed_url(self, context, grant_id: int, payload: SignedUrlIssueRequest) -> SignedUrlLifecycleResponse:
        ...

    async def revoke_signed_url(self, context, grant_id: int) -> None:
        ...

    async def read_metadata(self, context, file_id: int) -> StorageFileResponse:
        ...

    async def write_metadata(self, context, file_id: int, payload: FileMetadataPatchRequest) -> StorageFileResponse:
        ...

    async def lifecycle_state(self, context, file_id: int) -> StorageLifecycleResponse:
        ...

    async def policy(self, context) -> StoragePolicyRead:
        ...

    async def create_retention_rule(self, context, payload: RetentionRuleCreate) -> RetentionRuleResponse:
        ...

    async def list_retention_rules(self, context) -> list[RetentionRuleResponse]:
        ...

    async def run_retention(self, context, *, now: datetime | None = None) -> RetentionExecutionResponse:
        ...

    async def delete_file(self, context, file_id: int) -> None:
        ...
