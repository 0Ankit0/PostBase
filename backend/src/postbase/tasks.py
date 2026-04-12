from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlmodel import select

from src.apps.core.celery_app import celery_app  # noqa: F401
from src.db.session import async_session_factory
from src.postbase.capabilities.events.webhook_jobs import process_due_webhook_jobs
from src.postbase.domain.models import EventChannel, WebhookDeliveryJob

logger = logging.getLogger(__name__)


async def drain_due_webhook_jobs(limit: int = 200, *, environment_id: int | None = None) -> int:
    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        due_job_filters = [
            WebhookDeliveryJob.status.in_(["pending", "retrying"]),
            WebhookDeliveryJob.next_attempt_at.is_not(None),
            WebhookDeliveryJob.next_attempt_at <= now,
        ]
        if environment_id is not None:
            channel_ids = (
                await db.execute(
                    select(EventChannel.id).where(EventChannel.environment_id == environment_id)
                )
            ).scalars().all()
            if not channel_ids:
                return 0
            due_job_filters.append(WebhookDeliveryJob.channel_id.in_(channel_ids))

        due_job_ids = (
            await db.execute(
                select(WebhookDeliveryJob.id)
                .where(*due_job_filters)
                .order_by(WebhookDeliveryJob.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        if not due_job_ids:
            return 0

        records = await process_due_webhook_jobs(db, limit=limit, job_ids=due_job_ids)
        await db.commit()
        return len(records)


@shared_task(name="postbase_process_webhook_delivery_jobs_task")
def process_webhook_delivery_jobs_task(limit: int = 200) -> int:
    try:
        return asyncio.run(drain_due_webhook_jobs(limit))
    except Exception as exc:
        logger.exception("Failed processing webhook delivery jobs: %s", exc)
        return 0
