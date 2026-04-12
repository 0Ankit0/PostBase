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
