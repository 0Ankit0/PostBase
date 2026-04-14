from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from src.postbase.capabilities.events.webhook_jobs import (
    enqueue_webhook_job,
    process_due_webhook_jobs,
    replay_dead_letter_webhook_jobs,
)
from src.postbase.domain.models import (
    DeadLetterWebhookDelivery,
    EventChannel,
    Subscription,
    WebhookDeliveryJob,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_webhook_delivery_transient_failure_then_success(db_session):
    channel = EventChannel(environment_id=1, channel_key="retries", description="")
    db_session.add(channel)
    await db_session.flush()
    subscription = Subscription(
        channel_id=channel.id,
        target_type="webhook",
        target_ref="https://hooks.example.com/transient-fail",
        config_json={},
    )
    db_session.add(subscription)
    await db_session.flush()

    job = await enqueue_webhook_job(
        db_session,
        channel_id=channel.id,
        subscription_id=subscription.id,
        event_name="deploy.started",
        payload_json={"id": "evt_1"},
        target_ref=subscription.target_ref,
        max_attempts=3,
    )

    first_records = await process_due_webhook_jobs(db_session, channel_id=channel.id)
    assert len(first_records) == 1
    await db_session.refresh(job)
    assert job.status == "retrying"
    assert job.attempt_count == 1
    assert job.latest_response_code == 503
    assert len(job.attempt_history_json) == 1
    assert job.next_attempt_at is not None
    first_delay_seconds = int((_as_utc(job.next_attempt_at) - datetime.now(timezone.utc)).total_seconds())
    assert 0 <= first_delay_seconds <= 1

    job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()
    second_records = await process_due_webhook_jobs(db_session, channel_id=channel.id)
    assert len(second_records) == 1
    await db_session.refresh(job)
    assert job.status == "delivered"
    assert job.attempt_count == 2
    assert job.latest_response_code == 200
    assert len(job.attempt_history_json) == 2

    dead_letter_rows = (await db_session.execute(select(DeadLetterWebhookDelivery))).scalars().all()
    assert dead_letter_rows == []


@pytest.mark.asyncio
async def test_webhook_delivery_permanent_failure_moves_to_dead_letter(db_session):
    channel = EventChannel(environment_id=1, channel_key="dead-letters", description="")
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
        event_name="deploy.failed",
        payload_json={"id": "evt_2"},
        target_ref=subscription.target_ref,
        max_attempts=2,
    )

    await process_due_webhook_jobs(db_session, channel_id=channel.id)
    job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()
    records = await process_due_webhook_jobs(db_session, channel_id=channel.id)
    assert records[-1].status == "failed"

    await db_session.refresh(job)
    assert job.status == "dead_lettered"
    assert job.attempt_count == 2
    assert len(job.attempt_history_json) == 2

    dead_letter = (
        await db_session.execute(select(DeadLetterWebhookDelivery).where(
            DeadLetterWebhookDelivery.webhook_delivery_job_id == job.id
        ))
    ).scalars().one()
    assert dead_letter.attempt_count == 2
    assert dead_letter.latest_response_code == 500
    assert dead_letter.dead_letter_state == "active"
    assert len(dead_letter.attempt_history_json) == 2


@pytest.mark.asyncio
async def test_replay_dead_letter_webhook_job_succeeds(db_session):
    channel = EventChannel(environment_id=1, channel_key="replay", description="")
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
        event_name="deploy.retryable",
        payload_json={"id": "evt_3"},
        target_ref=subscription.target_ref,
        max_attempts=1,
    )
    await process_due_webhook_jobs(db_session, channel_id=channel.id)
    await db_session.refresh(job)
    assert job.status == "dead_lettered"

    job.target_ref = "https://hooks.example.com/recovered"
    await db_session.flush()
    replayed = await replay_dead_letter_webhook_jobs(db_session, limit=10)
    assert replayed.scanned_failed_jobs == 1
    assert replayed.requeued_jobs == 1
    assert replayed.skipped_jobs == 0
    assert replayed.reasons["requeued"] == 1
    await db_session.refresh(job)
    assert job.status == "retrying"
    assert job.next_attempt_at is not None

    job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()
    await process_due_webhook_jobs(db_session, channel_id=channel.id)
    await db_session.refresh(job)
    assert job.status == "delivered"

    dead_letter = (
        await db_session.execute(select(DeadLetterWebhookDelivery).where(
            DeadLetterWebhookDelivery.webhook_delivery_job_id == job.id
        ))
    ).scalars().one()
    assert dead_letter.dead_letter_state == "replayed"
    assert dead_letter.replayed_at is not None

    refreshed_job = await db_session.get(WebhookDeliveryJob, job.id)
    assert refreshed_job is not None
    assert refreshed_job.latest_response_code == 200


@pytest.mark.asyncio
async def test_replay_dead_letter_is_not_duplicated_when_job_already_recovered(db_session):
    channel = EventChannel(environment_id=1, channel_key="replay-safe", description="")
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
        event_name="deploy.retry-safe",
        payload_json={"id": "evt_4"},
        target_ref=subscription.target_ref,
        max_attempts=1,
    )
    await process_due_webhook_jobs(db_session, channel_id=channel.id)
    await db_session.refresh(job)
    assert job.status == "dead_lettered"

    first_recovery = await replay_dead_letter_webhook_jobs(db_session, limit=10)
    assert first_recovery.requeued_jobs == 1
    assert first_recovery.skipped_jobs == 0

    second_recovery = await replay_dead_letter_webhook_jobs(db_session, limit=10)
    assert second_recovery.scanned_failed_jobs == 0
    assert second_recovery.requeued_jobs == 0
    assert second_recovery.skipped_jobs == 0
