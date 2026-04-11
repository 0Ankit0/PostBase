from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.domain.models import IdempotencyRecord


@dataclass
class IdempotencyReplay:
    status_code: int
    response_json: dict[str, Any]


class IdempotencyService:
    @staticmethod
    def build_request_hash(payload: Any) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    async def check_replay_or_conflict(
        db: AsyncSession,
        *,
        idempotency_key: str,
        actor_user_id: int,
        endpoint_fingerprint: str,
        request_hash: str,
    ) -> IdempotencyReplay | None:
        existing = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.idempotency_key == idempotency_key,
                    IdempotencyRecord.actor_user_id == actor_user_id,
                    IdempotencyRecord.endpoint_fingerprint == endpoint_fingerprint,
                )
            )
        ).scalars().first()
        if existing is None:
            return None

        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "idempotency_key_payload_conflict",
                    "message": "idempotency_key_reused_with_different_payload",
                },
            )

        if existing.response_status_code is None or existing.response_json is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "idempotency_request_in_progress", "message": "request_in_progress"},
            )

        return IdempotencyReplay(
            status_code=existing.response_status_code,
            response_json=existing.response_json,
        )

    @staticmethod
    async def reserve_key(
        db: AsyncSession,
        *,
        idempotency_key: str,
        actor_user_id: int,
        endpoint_fingerprint: str,
        request_hash: str,
    ) -> IdempotencyRecord:
        now = datetime.now(timezone.utc)
        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            endpoint_fingerprint=endpoint_fingerprint,
            request_hash=request_hash,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        await db.flush()
        return record

    @staticmethod
    async def persist_success(
        db: AsyncSession,
        *,
        record: IdempotencyRecord,
        response_status_code: int,
        response_json: dict[str, Any],
    ) -> None:
        record.response_status_code = response_status_code
        record.response_json = response_json
        record.updated_at = datetime.now(timezone.utc)
        await db.flush()
