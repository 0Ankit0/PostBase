from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
from datetime import datetime
from typing import Literal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.domain.models import AuditLog


async def record_audit_event(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_user_id: int | None = None,
    tenant_id: int | None = None,
    project_id: int | None = None,
    environment_id: int | None = None,
    payload: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        project_id=project_id,
        environment_id=environment_id,
        payload_json=payload or {},
    )
    db.add(log)
    await db.flush()
    return log


async def record_transition_audit_event_once(
    db: AsyncSession,
    *,
    transition_key: str,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_user_id: int | None = None,
    tenant_id: int | None = None,
    project_id: int | None = None,
    environment_id: int | None = None,
    payload: dict | None = None,
) -> AuditLog:
    existing_rows = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.action == action,
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
        )
    ).scalars().all()
    for existing in existing_rows:
        existing_transition_key = (existing.payload_json or {}).get("transition_key")
        if existing_transition_key == transition_key:
            return existing

    merged_payload = {**(payload or {}), "transition_key": transition_key}
    return await record_audit_event(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        project_id=project_id,
        environment_id=environment_id,
        payload=merged_payload,
    )


async def record_auth_timeline_event(
    db: AsyncSession,
    *,
    event_name: str,
    subject: str,
    subject_id: str,
    actor_user_id: int | None = None,
    tenant_id: int | None = None,
    project_id: int | None = None,
    environment_id: int | None = None,
    payload: dict | None = None,
) -> AuditLog:
    normalized_payload = {
        "category": "auth",
        "event_name": event_name,
        "subject": subject,
        "subject_id": subject_id,
        **(payload or {}),
    }
    return await record_audit_event(
        db,
        action="auth.timeline",
        entity_type=subject,
        entity_id=subject_id,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        project_id=project_id,
        environment_id=environment_id,
        payload=normalized_payload,
    )


async def record_channel_policy_event(
    db: AsyncSession,
    *,
    context,
    channel_id: int,
    channel_key: str,
    previous_policy: dict,
    next_policy: dict,
) -> AuditLog:
    return await record_audit_event(
        db,
        action="events.channel_policy.updated",
        entity_type="event_channel",
        entity_id=str(channel_id),
        actor_user_id=getattr(context, "auth_user_id", None),
        tenant_id=context.project.tenant_id,
        project_id=context.project_id,
        environment_id=context.environment_id,
        payload={
            "channel_key": channel_key,
            "previous_policy": previous_policy,
            "next_policy": next_policy,
        },
    )


async def record_webhook_secret_rotation_event(
    db: AsyncSession,
    *,
    context,
    channel_id: int,
    subscription_id: int,
    grace_window_seconds: int,
) -> AuditLog:
    return await record_audit_event(
        db,
        action="events.webhook_secret.rotated",
        entity_type="event_webhook_endpoint",
        entity_id=str(subscription_id),
        actor_user_id=getattr(context, "auth_user_id", None),
        tenant_id=context.project.tenant_id,
        project_id=context.project_id,
        environment_id=context.environment_id,
        payload={
            "channel_id": channel_id,
            "grace_window_seconds": grace_window_seconds,
        },
    )


async def query_audit_logs(
    db: AsyncSession,
    *,
    project_id: int | None = None,
    environment_id: int | None = None,
    actor_user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[AuditLog], int]:
    filters = []
    if project_id is not None:
        filters.append(AuditLog.project_id == project_id)
    if environment_id is not None:
        filters.append(AuditLog.environment_id == environment_id)
    if actor_user_id is not None:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if action:
        filters.append(AuditLog.action == action)
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if entity_id:
        filters.append(AuditLog.entity_id == entity_id)
    if from_ts is not None:
        filters.append(AuditLog.created_at >= from_ts)
    if to_ts is not None:
        filters.append(AuditLog.created_at <= to_ts)

    total = (await db.execute(select(func.count()).select_from(AuditLog).where(*filters))).scalar_one()
    rows = (
        await db.execute(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return rows, total


def serialize_audit_export(
    rows: list[AuditLog],
    *,
    export_format: Literal["json", "csv"],
) -> str:
    payload = [
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "project_id": row.project_id,
            "environment_id": row.environment_id,
            "actor_user_id": row.actor_user_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "payload_json": row.payload_json,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
    if export_format == "json":
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "tenant_id",
            "project_id",
            "environment_id",
            "actor_user_id",
            "action",
            "entity_type",
            "entity_id",
            "payload_json",
            "created_at",
        ],
    )
    writer.writeheader()
    for item in payload:
        writer.writerow({**item, "payload_json": json.dumps(item["payload_json"], sort_keys=True)})
    return output.getvalue()


def build_compliance_evidence_bundle(
    rows: list[AuditLog],
    *,
    export_format: Literal["json", "csv"],
    scope: Literal["privileged", "migration"],
    signing_key: str,
) -> dict[str, object]:
    exported = serialize_audit_export(rows, export_format=export_format)
    digest = hashlib.sha256(exported.encode("utf-8")).hexdigest()
    signature = hmac.new(signing_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "scope": scope,
        "export_format": export_format,
        "record_count": len(rows),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "hash_sha256": digest,
        "signature_hmac_sha256": signature,
        "data": exported,
    }
