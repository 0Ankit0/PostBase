from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import select

from src.apps.core.config import settings
from src.postbase.capabilities.events.webhook_jobs import enqueue_webhook_job, process_due_webhook_jobs
from src.postbase.domain.models import EventChannel, Subscription, UsageMeter, WebhookDeliveryJob


@pytest.mark.asyncio
async def test_webhook_retry_ceiling_enforced(db_session):
    channel = EventChannel(environment_id=1, channel_key="ceiling", description="")
    db_session.add(channel)
    await db_session.flush()
    subscription = Subscription(
        channel_id=channel.id,
        target_type="webhook",
        target_ref="https://hooks.example.com/permanent-fail",
        config_json={},
    )
    db_session.add(subscription)
    await db_session.flush()

    job = await enqueue_webhook_job(
        db_session,
        channel_id=channel.id,
        subscription_id=subscription.id,
        event_name="drill.retry-ceiling",
        payload_json={"id": "evt_retries"},
        target_ref=subscription.target_ref,
        max_attempts=settings.POSTBASE_WEBHOOK_RETRY_CEILING + 10,
    )
    assert job.max_attempts == settings.POSTBASE_WEBHOOK_RETRY_CEILING


@pytest.mark.asyncio
async def test_webhook_circuit_breaker_halts_batch_processing(db_session, monkeypatch):
    monkeypatch.setattr(settings, "POSTBASE_WEBHOOK_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 1)

    channel = EventChannel(environment_id=1, channel_key="breaker", description="")
    db_session.add(channel)
    await db_session.flush()

    for idx in range(3):
        subscription = Subscription(
            channel_id=channel.id,
            target_type="webhook",
            target_ref=f"https://hooks.example.com/permanent-fail/{idx}",
            config_json={},
        )
        db_session.add(subscription)
        await db_session.flush()
        await enqueue_webhook_job(
            db_session,
            channel_id=channel.id,
            subscription_id=subscription.id,
            event_name="drill.circuit-breaker",
            payload_json={"id": f"evt_breaker_{idx}"},
            target_ref=subscription.target_ref,
            max_attempts=3,
        )

    records = await process_due_webhook_jobs(db_session, channel_id=channel.id, limit=10)
    assert len(records) == 1

    jobs = (
        await db_session.execute(select(WebhookDeliveryJob).where(WebhookDeliveryJob.channel_id == channel.id))
    ).scalars().all()
    attempted_jobs = [job for job in jobs if job.attempt_count > 0]
    assert len(attempted_jobs) == 1


@pytest.mark.asyncio
async def test_webhook_auth_anomaly_and_backlog_alert_metrics_recorded(db_session, monkeypatch):
    monkeypatch.setattr(settings, "POSTBASE_WEBHOOK_BACKLOG_ALERT_THRESHOLD", 1)

    channel = EventChannel(environment_id=1, channel_key="alerts", description="")
    db_session.add(channel)
    await db_session.flush()

    auth_fail_subscription = Subscription(
        channel_id=channel.id,
        target_type="webhook",
        target_ref="https://hooks.example.com/auth-fail",
        config_json={},
    )
    pending_subscription = Subscription(
        channel_id=channel.id,
        target_type="webhook",
        target_ref="https://hooks.example.com/transient-fail",
        config_json={},
    )
    db_session.add(auth_fail_subscription)
    db_session.add(pending_subscription)
    await db_session.flush()

    await enqueue_webhook_job(
        db_session,
        channel_id=channel.id,
        subscription_id=auth_fail_subscription.id,
        event_name="drill.auth-anomaly",
        payload_json={"id": "evt_auth"},
        target_ref=auth_fail_subscription.target_ref,
        max_attempts=2,
    )
    pending_job = await enqueue_webhook_job(
        db_session,
        channel_id=channel.id,
        subscription_id=pending_subscription.id,
        event_name="drill.backlog",
        payload_json={"id": "evt_backlog"},
        target_ref=pending_subscription.target_ref,
        max_attempts=2,
    )
    pending_job.next_attempt_at = datetime.now(timezone.utc)

    await process_due_webhook_jobs(db_session, channel_id=channel.id, limit=1)

    usage_rows = (
        await db_session.execute(
            select(UsageMeter).where(
                UsageMeter.environment_id == 1,
                UsageMeter.capability_key == "events",
            )
        )
    ).scalars().all()
    usage_by_key = {row.metric_key: row.value for row in usage_rows}

    assert usage_by_key.get("webhook_auth_anomaly_total", 0) >= 1
    assert usage_by_key.get("webhook_backlog_alert_total", 0) >= 1
