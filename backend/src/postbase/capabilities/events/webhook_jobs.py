from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.config import settings
from src.postbase.capabilities.events.webhook_delivery import deliver_webhook
from src.postbase.domain.models import (
    DeadLetterWebhookDelivery,
    DeliveryRecord,
    EventChannel,
    WebhookDeliveryJob,
)
from src.postbase.platform.usage import record_usage

ACTIVE_JOB_STATUSES = ("pending", "retrying")
TERMINAL_JOB_STATUSES = ("delivered", "dead_lettered")
BACKOFF_SCHEDULE_SECONDS = (1, 2, 4, 8, 16, 32, 60)


@dataclass
class DeadLetterReplayDiagnostics:
    scanned_failed_jobs: int
    requeued_jobs: int
    exhausted_job_ids: list[int]
    skipped_jobs: int
    skipped_job_ids: list[int]
    reasons: dict[str, int]


def _next_attempt_time(attempt_count: int, *, now: datetime) -> datetime:
    schedule_index = min(max(attempt_count - 1, 0), len(BACKOFF_SCHEDULE_SECONDS) - 1)
    backoff_seconds = BACKOFF_SCHEDULE_SECONDS[schedule_index]
    return now + timedelta(seconds=backoff_seconds)


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
    bounded_attempts = max(1, min(max_attempts, settings.POSTBASE_WEBHOOK_RETRY_CEILING))
    job = WebhookDeliveryJob(
        channel_id=channel_id,
        subscription_id=subscription_id,
        event_name=event_name,
        payload_json=payload_json,
        target_ref=target_ref,
        status="pending",
        max_attempts=bounded_attempts,
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
    job_ids: list[int] | None = None,
) -> list[DeliveryRecord]:
    now = datetime.now(timezone.utc)
    filters = [
        WebhookDeliveryJob.status.in_(ACTIVE_JOB_STATUSES),
        WebhookDeliveryJob.next_attempt_at <= now,
    ]
    if channel_id is not None:
        filters.append(WebhookDeliveryJob.channel_id == channel_id)
    if job_ids is not None:
        if not job_ids:
            return []
        filters.append(WebhookDeliveryJob.id.in_(job_ids))

    jobs = (
        await db.execute(
            select(WebhookDeliveryJob)
            .where(*filters)
            .order_by(WebhookDeliveryJob.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    delivery_records: list[DeliveryRecord] = []
    batch_failures = 0
    channel_environment_ids: dict[int, int] = {}

    for job in jobs:
        if batch_failures >= settings.POSTBASE_WEBHOOK_CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            break

        if job.status in TERMINAL_JOB_STATUSES:
            continue

        if job.attempt_count >= job.max_attempts:
            batch_failures += 1
            job.status = "dead_lettered"
            job.next_attempt_at = None
            job.error_text = "webhook delivery retry budget exhausted"
            job.updated_at = now
            if (
                await db.execute(
                    select(DeadLetterWebhookDelivery).where(
                        DeadLetterWebhookDelivery.webhook_delivery_job_id == job.id
                    )
                )
            ).scalars().first() is None:
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
                        error_text=job.error_text,
                        attempt_history_json=job.attempt_history_json,
                    )
                )
            continue

        result = await deliver_webhook(
            target_ref=job.target_ref,
            event_name=job.event_name,
            payload=job.payload_json,
            attempt_number=job.attempt_count + 1,
            timeout_ms=settings.POSTBASE_WEBHOOK_TIMEOUT_MS,
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

        metric_environment_id = await _resolve_metric_environment_id_cached(
            db,
            channel_id=job.channel_id,
            cache=channel_environment_ids,
        )
        if result.status == "delivered":
            batch_failures = 0
            job.status = "delivered"
            job.delivered_at = now
            job.next_attempt_at = None
            delivery_status = "delivered"
            delivered_at = now
            error_text = ""
            await record_usage(
                db,
                environment_id=metric_environment_id,
                capability_key="events",
                metric_key="webhook_delivery_success_total",
            )
        elif job.attempt_count >= job.max_attempts:
            batch_failures += 1
            job.status = "dead_lettered"
            job.next_attempt_at = None
            if (
                await db.execute(
                    select(DeadLetterWebhookDelivery).where(
                        DeadLetterWebhookDelivery.webhook_delivery_job_id == job.id
                    )
                )
            ).scalars().first() is None:
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
            await record_usage(
                db,
                environment_id=metric_environment_id,
                capability_key="events",
                metric_key="webhook_delivery_failed_total",
            )
        else:
            batch_failures += 1
            job.status = "retrying"
            job.next_attempt_at = _next_attempt_time(job.attempt_count, now=now)
            delivery_status = "retrying"
            delivered_at = None
            error_text = result.error_text or "webhook delivery retry scheduled"
            await record_usage(
                db,
                environment_id=metric_environment_id,
                capability_key="events",
                metric_key="webhook_delivery_retry_total",
            )

        if result.response_code == 401:
            await record_usage(
                db,
                environment_id=metric_environment_id,
                capability_key="events",
                metric_key="webhook_auth_anomaly_total",
            )

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
    await _record_queue_health_signals(db, channel_id=channel_id)
    return delivery_records


async def replay_dead_letter_webhook_jobs(
    db: AsyncSession,
    *,
    limit: int = 200,
) -> DeadLetterReplayDiagnostics:
    dead_letters = (
        await db.execute(
            select(DeadLetterWebhookDelivery)
            .where(DeadLetterWebhookDelivery.dead_letter_state == "active")
            .order_by(DeadLetterWebhookDelivery.dead_lettered_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    requeued_dead_letters: list[int] = []
    skipped_dead_letters: list[int] = []
    reasons: dict[str, int] = {
        "requeued": 0,
        "already_replayed": 0,
        "job_missing": 0,
        "job_not_dead_lettered": 0,
    }

    for dead_letter in dead_letters:
        if dead_letter.id is None:
            continue

        mark_replayed_result = await db.execute(
            update(DeadLetterWebhookDelivery)
            .where(
                DeadLetterWebhookDelivery.id == dead_letter.id,
                DeadLetterWebhookDelivery.dead_letter_state == "active",
            )
            .values(dead_letter_state="replayed", replayed_at=now)
        )
        if mark_replayed_result.rowcount != 1:
            skipped_dead_letters.append(dead_letter.id)
            reasons["already_replayed"] += 1
            continue

        job = await db.get(WebhookDeliveryJob, dead_letter.webhook_delivery_job_id)
        if job is None:
            skipped_dead_letters.append(dead_letter.id)
            reasons["job_missing"] += 1
            continue
        if job.status != "dead_lettered":
            skipped_dead_letters.append(dead_letter.id)
            reasons["job_not_dead_lettered"] += 1
            continue

        job.status = "retrying"
        job.next_attempt_at = now
        job.error_text = "operator initiated replay from dead-letter queue"
        job.updated_at = now
        requeued_dead_letters.append(dead_letter.id)
        reasons["requeued"] += 1

    await db.flush()
    return DeadLetterReplayDiagnostics(
        scanned_failed_jobs=len(dead_letters),
        requeued_jobs=len(requeued_dead_letters),
        exhausted_job_ids=requeued_dead_letters,
        skipped_jobs=len(skipped_dead_letters),
        skipped_job_ids=skipped_dead_letters,
        reasons=reasons,
    )


async def _record_queue_health_signals(db: AsyncSession, *, channel_id: int | None) -> None:
    pending_filters = [WebhookDeliveryJob.status.in_(["pending", "retrying"])]
    failed_filters = [WebhookDeliveryJob.status == "dead_lettered"]
    if channel_id is not None:
        pending_filters.append(WebhookDeliveryJob.channel_id == channel_id)
        failed_filters.append(WebhookDeliveryJob.channel_id == channel_id)

    pending_jobs = (
        await db.execute(select(WebhookDeliveryJob).where(*pending_filters))
    ).scalars().all()
    failed_jobs = (
        await db.execute(select(WebhookDeliveryJob).where(*failed_filters))
    ).scalars().all()
    backlog_size = len(pending_jobs)
    failed_size = len(failed_jobs)

    metric_scope_id = await _resolve_metric_environment_id(db, channel_id=channel_id)
    if backlog_size >= settings.POSTBASE_WEBHOOK_BACKLOG_ALERT_THRESHOLD:
        await record_usage(
            db,
            environment_id=metric_scope_id,
            capability_key="events",
            metric_key="webhook_backlog_alert_total",
        )
    if failed_size >= settings.POSTBASE_WEBHOOK_DELIVERY_FAILURE_ALERT_THRESHOLD:
        await record_usage(
            db,
            environment_id=metric_scope_id,
            capability_key="events",
            metric_key="webhook_delivery_failure_alert_total",
        )


async def _resolve_metric_environment_id(db: AsyncSession, *, channel_id: int | None) -> int:
    if channel_id is None:
        first_channel = (await db.execute(select(EventChannel).limit(1))).scalars().first()
        return first_channel.environment_id if first_channel else 1
    channel = await db.get(EventChannel, channel_id)
    if channel is not None:
        return channel.environment_id
    first_channel = (await db.execute(select(EventChannel).limit(1))).scalars().first()
    return first_channel.environment_id if first_channel else 1


async def _resolve_metric_environment_id_cached(
    db: AsyncSession,
    *,
    channel_id: int,
    cache: dict[int, int],
) -> int:
    if channel_id in cache:
        return cache[channel_id]
    value = await _resolve_metric_environment_id(db, channel_id=channel_id)
    cache[channel_id] = value
    return value
