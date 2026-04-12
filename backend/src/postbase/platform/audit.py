from __future__ import annotations

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
