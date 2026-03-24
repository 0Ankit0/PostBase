from __future__ import annotations

from datetime import timezone, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.domain.models import UsageMeter


async def record_usage(
    db: AsyncSession,
    *,
    environment_id: int,
    capability_key: str,
    metric_key: str,
    increment: float = 1.0,
) -> UsageMeter:
    row = (
        await db.execute(
            select(UsageMeter).where(
                UsageMeter.environment_id == environment_id,
                UsageMeter.capability_key == capability_key,
                UsageMeter.metric_key == metric_key,
            )
        )
    ).scalars().first()
    if row is None:
        row = UsageMeter(
            environment_id=environment_id,
            capability_key=capability_key,
            metric_key=metric_key,
            value=0.0,
        )
        db.add(row)
        await db.flush()
    row.value += increment
    row.measured_at = datetime.now(timezone.utc)
    await db.flush()
    return row
