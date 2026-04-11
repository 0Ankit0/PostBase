from __future__ import annotations

import base64
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.config import settings
from src.apps.core.schemas import PaginatedResponse
from src.apps.core.storage import delete_media, save_media_bytes
from src.postbase.capabilities.storage.contracts import (
    SignedUrlResponse,
    StorageFileResponse,
    StorageUploadRequest,
)
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import FileObject
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


class LocalDiskStorageProvider:
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.STORAGE,
            provider_key="local-disk",
            supported_operations=["upload", "list", "signed_url", "delete"],
            optional_features=["local-filesystem"],
            limits={"max_filename_length": 255},
        )

    async def health(self) -> ProviderHealth:
        media_path = Path(settings.MEDIA_DIR)
        ready = media_path.exists() or media_path.parent.exists()
        detail = f"media_dir={media_path}"
        return ProviderHealth(ready=ready, detail=detail)

    async def upload_file(self, context, payload: StorageUploadRequest) -> StorageFileResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        try:
            content = base64.b64decode(payload.content_base64.encode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 content") from exc

        owner_segment = f"user-{context.auth_user_id}" if context.auth_user_id else "public"
        relative_path = (
            f"postbase/{context.project_id}/{context.environment_id}/"
            f"{payload.bucket_key}/{owner_segment}/{payload.filename}"
        )
        url = save_media_bytes(relative_path, content, content_type=payload.content_type)
        file_object = FileObject(
            environment_id=context.environment_id,
            namespace=payload.namespace,
            bucket_key=payload.bucket_key,
            path=relative_path,
            filename=payload.filename,
            content_type=payload.content_type,
            size_bytes=len(content),
            provider_object_ref=url,
            owner_auth_user_id=context.auth_user_id,
            metadata_json={**payload.metadata_json, "storage_provider": "local-disk"},
        )
        db.add(file_object)
        await db.flush()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.STORAGE.value,
            metric_key="upload_file",
        )
        await db.commit()
        return self._to_response(file_object)

    async def list_files(
        self,
        context,
        bucket_key: str | None = None,
        *,
        skip: int,
        limit: int,
    ) -> PaginatedResponse[StorageFileResponse]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        query = select(FileObject).where(FileObject.environment_id == context.environment_id)
        count_query = select(func.count()).select_from(FileObject).where(FileObject.environment_id == context.environment_id)
        if bucket_key:
            query = query.where(FileObject.bucket_key == bucket_key)
            count_query = count_query.where(FileObject.bucket_key == bucket_key)
        if not context.service_role:
            visibility_predicate = or_(FileObject.owner_auth_user_id == None, FileObject.owner_auth_user_id == context.auth_user_id)
            query = query.where(visibility_predicate)
            count_query = count_query.where(visibility_predicate)
        total = (await db.execute(count_query)).scalar_one()
        rows = (await db.execute(query.order_by(FileObject.id.desc()).offset(skip).limit(limit))).scalars().all()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.STORAGE.value,
            metric_key="list_files",
        )
        return PaginatedResponse[StorageFileResponse].create(
            items=[self._to_response(item) for item in rows],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def signed_url(self, context, file_id: int) -> SignedUrlResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await db.get(FileObject, file_id)
        if row is None or row.environment_id != context.environment_id or not self._can_access(context, row):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.STORAGE.value,
            metric_key="signed_url",
        )
        return SignedUrlResponse(file_id=row.id, url=row.provider_object_ref)

    async def delete_file(self, context, file_id: int) -> None:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await db.get(FileObject, file_id)
        if row is None or row.environment_id != context.environment_id or not self._can_access(context, row):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        delete_media(row.path)
        await db.delete(row)
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.STORAGE.value,
            metric_key="delete_file",
        )
        await db.commit()

    def _to_response(self, row: FileObject) -> StorageFileResponse:
        return StorageFileResponse(
            id=row.id,
            bucket_key=row.bucket_key,
            path=row.path,
            filename=row.filename,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            url=row.provider_object_ref,
            metadata_json=row.metadata_json,
        )

    def _can_access(self, context, row: FileObject) -> bool:
        if context.service_role:
            return True
        if row.owner_auth_user_id is None:
            return True
        return row.owner_auth_user_id == context.auth_user_id
