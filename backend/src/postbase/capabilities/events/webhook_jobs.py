from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.postbase.capabilities.events.webhook_delivery import deliver_webhook
from src.postbase.domain.models import DeadLetterWebhookDelivery, DeliveryRecord, WebhookDeliveryJob


def _next_attempt_time(attempt_count: int) -> datetime:
    # Simple bounded exponential backoff in seconds.
    backoff_seconds = min(60, 2 ** max(0, attempt_count - 1))
    return datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)


async def enqueue_webhook_job(
    db: AsyncSession,
    *,
    channel_id: int,
    subscription_id: int,
    event_name: str,
    payload_json: dict,
    target_ref: str,
    max_attempts: int = 3,
) -> WebhookDeliveryJob:
    job = WebhookDeliveryJob(
        channel_id=channel_id,
        subscription_id=subscription_id,
        event_name=event_name,
        payload_json=payload_json,
        target_ref=target_ref,
        status="pending",
        max_attempts=max_attempts,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()
    return job


async def process_due_webhook_jobs(
    db: AsyncSession,
    *,
    channel_id: int | None = None,
    limit: int = 50,
) -> list[DeliveryRecord]:
    now = datetime.now(timezone.utc)
    filters = [
        WebhookDeliveryJob.status.in_(["pending", "retrying"]),
        WebhookDeliveryJob.next_attempt_at <= now,
    ]
    if channel_id is not None:
        filters.append(WebhookDeliveryJob.channel_id == channel_id)

    jobs = (
        await db.execute(
            select(WebhookDeliveryJob)
            .where(*filters)
            .order_by(WebhookDeliveryJob.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    delivery_records: list[DeliveryRecord] = []

    for job in jobs:
        result = await deliver_webhook(
            target_ref=job.target_ref,
            event_name=job.event_name,
            payload=job.payload_json,
            attempt_number=job.attempt_count + 1,
        )
        job.attempt_count += 1
        job.error_text = result.error_text
        job.latest_response_code = result.response_code
        job.latest_latency_ms = result.latency_ms
        job.attempt_history_json = [
            *job.attempt_history_json,
            {
                "attempt_number": job.attempt_count,
                "response_code": result.response_code,
                "latency_ms": result.latency_ms,
                "error_text": result.error_text,
                "attempted_at": now.isoformat(),
            },
        ]
        job.updated_at = now

        if result.status == "delivered":
            job.status = "delivered"
            job.delivered_at = now
            job.next_attempt_at = None
            delivery_status = "delivered"
            delivered_at = now
            error_text = ""
        elif job.attempt_count >= job.max_attempts:
            job.status = "dead_lettered"
            job.next_attempt_at = None
            db.add(
                DeadLetterWebhookDelivery(
                    webhook_delivery_job_id=job.id,
                    channel_id=job.channel_id,
                    subscription_id=job.subscription_id,
                    event_name=job.event_name,
                    payload_json=job.payload_json,
                    target_ref=job.target_ref,
                    attempt_count=job.attempt_count,
                    max_attempts=job.max_attempts,
                    latest_response_code=job.latest_response_code,
                    latest_latency_ms=job.latest_latency_ms,
                    error_text=result.error_text or "webhook delivery failed after retries",
                    attempt_history_json=job.attempt_history_json,
                )
            )
            delivery_status = "failed"
            delivered_at = None
            error_text = result.error_text or "webhook delivery failed after retries"
        else:
            job.status = "retrying"
            job.next_attempt_at = _next_attempt_time(job.attempt_count)
            delivery_status = "retrying"
            delivered_at = None
            error_text = result.error_text or "webhook delivery retry scheduled"

        record = DeliveryRecord(
            channel_id=job.channel_id,
            subscription_id=job.subscription_id,
            event_name=job.event_name,
            status=delivery_status,
            attempt_count=job.attempt_count,
            delivered_at=delivered_at,
            error_text=error_text,
            payload_json=job.payload_json,
        )
        db.add(record)
        delivery_records.append(record)

    await db.flush()
    return delivery_records


async def replay_dead_letter_webhook_jobs(
    db: AsyncSession,
    *,
    limit: int = 200,
) -> list[DeadLetterWebhookDelivery]:
    dead_letters = (
        await db.execute(
            select(DeadLetterWebhookDelivery)
            .where(DeadLetterWebhookDelivery.dead_letter_state == "active")
            .order_by(DeadLetterWebhookDelivery.dead_lettered_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for dead_letter in dead_letters:
        job = await db.get(WebhookDeliveryJob, dead_letter.webhook_delivery_job_id)
        if job is None:
            continue
        job.status = "retrying"
        job.next_attempt_at = now
        job.error_text = "operator initiated replay from dead-letter queue"
        job.updated_at = now
        dead_letter.dead_letter_state = "replayed"
        dead_letter.replayed_at = now
    await db.flush()
    return dead_letters
