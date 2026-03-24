from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

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
