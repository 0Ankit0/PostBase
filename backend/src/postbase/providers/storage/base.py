from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.schemas import PaginatedResponse
from src.apps.core.storage import delete_media, save_media_bytes
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
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import FileObject, StorageRetentionRule, StorageSignedUrlGrant
from src.postbase.platform.audit import record_audit_event
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


def _ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class StorageProviderBase:
    provider_key: str = "base"

    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.STORAGE,
            provider_key=self.provider_key,
            supported_operations=[
                "upload",
                "upload_init",
                "list",
                "signed_url",
                "signed_url_issue",
                "signed_url_refresh",
                "signed_url_revoke",
                "metadata_read",
                "metadata_write",
                "lifecycle",
                "policy",
                "retention_rules",
                "retention_execute",
                "delete",
            ],
            optional_features=["signed-access", "retention-policy"],
            validation_checks=["required_operations", "signed_url_ttl_limit", "required_secrets"],
            required_secret_kinds=[],
            limits={"max_filename_length": 255, "max_signed_url_ttl_seconds": 86_400},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(ready=True, detail=f"storage_provider={self.provider_key}")

    async def upload_file(self, context, payload: StorageUploadRequest) -> StorageFileResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        try:
            content = base64.b64decode(payload.content_base64.encode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 content") from exc

        row = await self._persist_file(
            db,
            context=context,
            filename=payload.filename,
            content=content,
            content_type=payload.content_type,
            bucket_key=payload.bucket_key,
            namespace=payload.namespace,
            metadata={**payload.metadata_json, "storage_provider": self.provider_key},
        )
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.STORAGE.value, metric_key="upload_file")
        await db.commit()
        return self._to_response(row)

    async def init_upload(self, context, payload: StorageUploadInitRequest) -> SignedUrlResponse:
        max_ttl = int(self.profile().limits.get("max_signed_url_ttl_seconds", 3600))
        ttl = min(payload.expires_in_seconds, max_ttl)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        token = secrets.token_urlsafe(24)
        base_url = getattr(context, "base_url", "http://localhost")
        upload_url = f"{base_url.rstrip('/')}/api/v1/storage/uploads/{token}"
        return SignedUrlResponse(file_id=0, url=upload_url, expires_at=expires_at, token=token, access_mode="write")

    async def list_files(self, context, bucket_key: str | None = None, *, skip: int, limit: int) -> PaginatedResponse[StorageFileResponse]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        query = select(FileObject).where(FileObject.environment_id == context.environment_id)
        count_query = select(func.count()).select_from(FileObject).where(FileObject.environment_id == context.environment_id)
        if bucket_key:
            query = query.where(FileObject.bucket_key == bucket_key)
            count_query = count_query.where(FileObject.bucket_key == bucket_key)
        if not context.service_role:
            predicate = or_(FileObject.owner_auth_user_id == None, FileObject.owner_auth_user_id == context.auth_user_id)
            query = query.where(predicate)
            count_query = count_query.where(predicate)
        total = (await db.execute(count_query)).scalar_one()
        rows = (await db.execute(query.order_by(FileObject.id.desc()).offset(skip).limit(limit))).scalars().all()
        return PaginatedResponse[StorageFileResponse].create(items=[self._to_response(row) for row in rows], total=total, skip=skip, limit=limit)

    async def signed_url(self, context, file_id: int) -> SignedUrlResponse:
        response = await self.issue_signed_url(context, file_id, SignedUrlIssueRequest())
        return SignedUrlResponse(
            file_id=response.file_id,
            url=response.url,
            expires_at=response.expires_at,
            grant_id=response.grant_id,
            token=response.token,
            access_mode=response.access_mode,  # type: ignore[arg-type]
        )

    async def issue_signed_url(self, context, file_id: int, payload: SignedUrlIssueRequest) -> SignedUrlLifecycleResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await self._require_file_access(db, context, file_id)
        max_ttl = int(self.profile().limits.get("max_signed_url_ttl_seconds", 3600))
        ttl = min(payload.expires_in_seconds, max_ttl)
        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(24)
        grant = StorageSignedUrlGrant(
            environment_id=context.environment_id,
            file_object_id=row.id,
            access_mode=payload.access_mode,
            token_hash=self._hash_token(token),
            expires_at=now + timedelta(seconds=ttl),
            issued_by_auth_user_id=context.auth_user_id,
        )
        db.add(grant)
        await db.flush()
        await record_audit_event(
            db,
            action="storage.signed_url_issued",
            entity_type="file_object",
            entity_id=str(row.id),
            actor_user_id=context.auth_user_id,
            project_id=context.project_id,
            environment_id=context.environment_id,
            payload={"grant_id": grant.id, "access_mode": payload.access_mode, "ttl": ttl},
        )
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.STORAGE.value, metric_key="signed_url")
        await db.commit()
        return self._grant_response(context, row, grant, token)

    async def refresh_signed_url(self, context, grant_id: int, payload: SignedUrlIssueRequest) -> SignedUrlLifecycleResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        grant = await db.get(StorageSignedUrlGrant, grant_id)
        now = datetime.now(timezone.utc)
        if grant is None or grant.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signed URL grant not found")
        if grant.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Signed URL grant already revoked")
        if _ensure_utc_datetime(grant.expires_at) <= now:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Signed URL grant expired")
        old_row = await self._require_file_access(db, context, grant.file_object_id)
        grant.revoked_at = now
        grant.updated_at = now
        await db.flush()
        return await self.issue_signed_url(context, old_row.id, payload)

    async def revoke_signed_url(self, context, grant_id: int) -> None:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        grant = await db.get(StorageSignedUrlGrant, grant_id)
        if grant is None or grant.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signed URL grant not found")
        if grant.revoked_at is None:
            grant.revoked_at = datetime.now(timezone.utc)
            grant.updated_at = datetime.now(timezone.utc)
            await record_audit_event(
                db,
                action="storage.signed_url_revoked",
                entity_type="storage_signed_url_grant",
                entity_id=str(grant.id),
                actor_user_id=context.auth_user_id,
                project_id=context.project_id,
                environment_id=context.environment_id,
                payload={"file_id": grant.file_object_id},
            )
            await db.commit()

    async def read_metadata(self, context, file_id: int) -> StorageFileResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await self._require_file_access(db, context, file_id)
        return self._to_response(row)

    async def write_metadata(self, context, file_id: int, payload: FileMetadataPatchRequest) -> StorageFileResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await self._require_file_access(db, context, file_id)
        row.metadata_json = {**row.metadata_json, **payload.metadata_json}
        await db.flush()
        await db.commit()
        return self._to_response(row)

    async def lifecycle_state(self, context, file_id: int) -> StorageLifecycleResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await self._require_file_access(db, context, file_id)
        detail = "active"
        if row.metadata_json.get("deleted"):
            detail = "deleted"
        return StorageLifecycleResponse(file_id=row.id, lifecycle_state=detail, detail=f"provider={self.provider_key}")

    async def policy(self, context) -> StoragePolicyRead:
        rules = await self.list_retention_rules(context)
        return StoragePolicyRead(
            max_signed_url_ttl_seconds=int(self.profile().limits.get("max_signed_url_ttl_seconds", 3600)),
            retention_rules=[rule.model_dump(mode="json") for rule in rules],
        )

    async def create_retention_rule(self, context, payload: RetentionRuleCreate) -> RetentionRuleResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        existing = (
            await db.execute(
                select(StorageRetentionRule).where(
                    StorageRetentionRule.environment_id == context.environment_id,
                    StorageRetentionRule.bucket_key == payload.bucket_key,
                    StorageRetentionRule.namespace == payload.namespace,
                )
            )
        ).scalars().first()
        now = datetime.now(timezone.utc)
        if existing is None:
            existing = StorageRetentionRule(
                environment_id=context.environment_id,
                bucket_key=payload.bucket_key,
                namespace=payload.namespace,
                max_age_days=payload.max_age_days,
                sweep_interval_minutes=payload.sweep_interval_minutes,
                enabled=payload.enabled,
                next_run_at=now,
            )
            db.add(existing)
        else:
            existing.max_age_days = payload.max_age_days
            existing.sweep_interval_minutes = payload.sweep_interval_minutes
            existing.enabled = payload.enabled
            existing.next_run_at = now
            existing.updated_at = now
        await db.flush()
        await db.commit()
        return self._retention_rule_response(existing)

    async def list_retention_rules(self, context) -> list[RetentionRuleResponse]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        rows = (
            await db.execute(
                select(StorageRetentionRule)
                .where(StorageRetentionRule.environment_id == context.environment_id)
                .order_by(StorageRetentionRule.id.asc())
            )
        ).scalars().all()
        return [self._retention_rule_response(row) for row in rows]

    async def run_retention(self, context, *, now: datetime | None = None) -> RetentionExecutionResponse:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        now = now or datetime.now(timezone.utc)
        rules = (
            await db.execute(
                select(StorageRetentionRule).where(
                    StorageRetentionRule.environment_id == context.environment_id,
                    StorageRetentionRule.enabled == True,
                    (StorageRetentionRule.next_run_at.is_(None) | (StorageRetentionRule.next_run_at <= now)),
                )
            )
        ).scalars().all()
        deleted = 0
        scanned = 0
        for rule in rules:
            threshold = now - timedelta(days=rule.max_age_days)
            files = (
                await db.execute(
                    select(FileObject).where(
                        FileObject.environment_id == context.environment_id,
                        FileObject.bucket_key == rule.bucket_key,
                        FileObject.namespace == rule.namespace,
                        FileObject.created_at <= threshold,
                    )
                )
            ).scalars().all()
            scanned += len(files)
            for row in files:
                delete_media(row.path)
                await db.delete(row)
                deleted += 1
            rule.last_run_at = now
            rule.next_run_at = now + timedelta(minutes=rule.sweep_interval_minutes)
            rule.updated_at = now
        expired_grants = (
            await db.execute(
                select(StorageSignedUrlGrant).where(
                    StorageSignedUrlGrant.environment_id == context.environment_id,
                    StorageSignedUrlGrant.revoked_at.is_(None),
                    StorageSignedUrlGrant.expires_at <= now,
                )
            )
        ).scalars().all()
        for grant in expired_grants:
            grant.revoked_at = now
            grant.updated_at = now
        if rules:
            await record_audit_event(
                db,
                action="storage.retention_executed",
                entity_type="storage_retention_rule",
                entity_id=str(context.environment_id),
                actor_user_id=context.auth_user_id,
                project_id=context.project_id,
                environment_id=context.environment_id,
                payload={"rule_count": len(rules), "deleted": deleted, "scanned": scanned, "expired_grants_revoked": len(expired_grants)},
            )
        await db.commit()
        return RetentionExecutionResponse(scanned_files=scanned, deleted_files=deleted, updated_rules=len(rules))

    async def delete_file(self, context, file_id: int) -> None:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await self._require_file_access(db, context, file_id)
        delete_media(row.path)
        await db.delete(row)
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.STORAGE.value, metric_key="delete_file")
        await db.commit()

    async def _persist_file(self, db: AsyncSession, *, context, filename: str, content: bytes, content_type: str, bucket_key: str, namespace: str, metadata: dict) -> FileObject:
        owner_segment = f"user-{context.auth_user_id}" if context.auth_user_id else "public"
        relative_path = f"postbase/{context.project_id}/{context.environment_id}/{bucket_key}/{owner_segment}/{filename}"
        url = save_media_bytes(relative_path, content, content_type=content_type)
        row = FileObject(
            environment_id=context.environment_id,
            namespace=namespace,
            bucket_key=bucket_key,
            path=relative_path,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            provider_object_ref=url,
            owner_auth_user_id=context.auth_user_id,
            metadata_json=metadata,
        )
        db.add(row)
        await db.flush()
        return row

    async def _require_file_access(self, db: AsyncSession, context, file_id: int) -> FileObject:
        row = await db.get(FileObject, file_id)
        if row is None or row.environment_id != context.environment_id or not self._can_access(context, row):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return row

    def _grant_response(self, context, row: FileObject, grant: StorageSignedUrlGrant, token: str) -> SignedUrlLifecycleResponse:
        url = f"{row.provider_object_ref}?grant={grant.id}&token={token}"
        return SignedUrlLifecycleResponse(
            grant_id=grant.id,
            file_id=row.id,
            access_mode=grant.access_mode,
            token=token,
            url=url,
            expires_at=grant.expires_at,
            revoked_at=grant.revoked_at,
        )

    def _retention_rule_response(self, row: StorageRetentionRule) -> RetentionRuleResponse:
        return RetentionRuleResponse(
            id=row.id,
            bucket_key=row.bucket_key,
            namespace=row.namespace,
            max_age_days=row.max_age_days,
            sweep_interval_minutes=row.sweep_interval_minutes,
            enabled=row.enabled,
            next_run_at=row.next_run_at,
            last_run_at=row.last_run_at,
        )

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

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _can_access(self, context, row: FileObject) -> bool:
        if context.service_role:
            return True
        if row.owner_auth_user_id is None:
            return True
        return row.owner_auth_user_id == context.auth_user_id
