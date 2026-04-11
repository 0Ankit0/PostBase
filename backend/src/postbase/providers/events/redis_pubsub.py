from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from src.apps.core.schemas import PaginatedResponse
from src.apps.core.config import settings
from src.apps.websocket.manager import manager as ws_manager
from src.postbase.capabilities.events.contracts import (
    ChannelCreateRequest,
    ChannelRead,
    DeliveryRead,
    EventPublishRequest,
    SubscriptionCreateRequest,
    SubscriptionRead,
    SubscriptionUpdateRequest,
)
from src.postbase.capabilities.events.validation import validate_subscription_configuration
from src.postbase.capabilities.events.webhook_jobs import enqueue_webhook_job, process_due_webhook_jobs
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import DeliveryRecord, EventChannel, Subscription
from src.postbase.platform.access import validate_identifier
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


class RedisPubSubEventsProvider:
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.EVENTS,
            provider_key="redis-pubsub",
            supported_operations=["channels", "subscriptions", "publish"],
            optional_features=["room-delivery"],
            limits={"max_room_name_length": 80},
        )

    async def health(self) -> ProviderHealth:
        detail = f"redis_url={settings.REDIS_URL} rooms={len(ws_manager.rooms_stats)}"
        return ProviderHealth(ready=True, detail=detail)

    async def create_channel(self, context, payload: ChannelCreateRequest) -> ChannelRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel_key = validate_identifier(payload.channel_key, "Channel key")
        existing = (
            await db.execute(
                select(EventChannel).where(
                    EventChannel.environment_id == context.environment_id,
                    EventChannel.channel_key == channel_key,
                )
            )
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Channel already exists")
        row = EventChannel(
            environment_id=context.environment_id,
            channel_key=channel_key,
            description=payload.description,
        )
        db.add(row)
        await db.flush()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.EVENTS.value,
            metric_key="create_channel",
        )
        await db.commit()
        return ChannelRead(id=row.id, channel_key=row.channel_key, description=row.description)

    async def list_channels(self, context, *, skip: int, limit: int) -> PaginatedResponse[ChannelRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        total = (
            await db.execute(
                select(func.count()).select_from(EventChannel).where(EventChannel.environment_id == context.environment_id)
            )
        ).scalar_one()
        rows = (
            await db.execute(
                select(EventChannel)
                .where(EventChannel.environment_id == context.environment_id)
                .order_by(EventChannel.id.desc())
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.EVENTS.value,
            metric_key="list_channels",
        )
        return PaginatedResponse[ChannelRead].create(
            items=[ChannelRead(id=row.id, channel_key=row.channel_key, description=row.description) for row in rows],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def create_subscription(self, context, channel_id: int, payload: SubscriptionCreateRequest) -> SubscriptionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await db.get(EventChannel, channel_id)
        if channel is None or channel.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        payload = validate_subscription_configuration(context, payload)
        row = Subscription(
            channel_id=channel.id,
            target_type=payload.target_type,
            target_ref=payload.target_ref,
            config_json=payload.config_json,
        )
        db.add(row)
        await db.flush()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.EVENTS.value,
            metric_key="create_subscription",
        )
        await db.commit()
        return SubscriptionRead(
            id=row.id,
            channel_id=row.channel_id,
            target_type=row.target_type,
            target_ref=row.target_ref,
            config_json=row.config_json,
            is_active=row.is_active,
        )

    async def update_subscription(self, context, subscription_id: int, payload: SubscriptionUpdateRequest) -> SubscriptionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await db.get(Subscription, subscription_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        channel = await db.get(EventChannel, row.channel_id)
        if channel is None or channel.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

        next_payload = SubscriptionCreateRequest(
            target_type=payload.target_type or row.target_type,
            target_ref=payload.target_ref or row.target_ref,
            config_json={**row.config_json, **(payload.config_json or {})},
        )
        validated = validate_subscription_configuration(context, next_payload)
        row.target_type = validated.target_type
        row.target_ref = validated.target_ref
        row.config_json = validated.config_json
        if payload.is_active is not None:
            row.is_active = payload.is_active

        await db.flush()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.EVENTS.value,
            metric_key="update_subscription",
        )
        await db.commit()
        return SubscriptionRead(
            id=row.id,
            channel_id=row.channel_id,
            target_type=row.target_type,
            target_ref=row.target_ref,
            config_json=row.config_json,
            is_active=row.is_active,
        )

    async def publish(self, context, channel_id: int, payload: EventPublishRequest) -> list[DeliveryRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await db.get(EventChannel, channel_id)
        if channel is None or channel.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        subscriptions = (
            await db.execute(
                select(Subscription).where(
                    Subscription.channel_id == channel.id,
                    Subscription.is_active == True,
                )
            )
        ).scalars().all()
        deliveries: list[DeliveryRecord] = []
        for subscription in subscriptions:
            status_value = "delivered"
            attempt_count = 1
            delivered_at = datetime.now(timezone.utc)
            error_text = ""
            if subscription.target_type == "room":
                await ws_manager.push_event_to_room(
                    subscription.target_ref,
                    payload.event_name,
                    payload.payload,
                )
            elif subscription.target_type == "webhook":
                await enqueue_webhook_job(
                    db,
                    channel_id=channel.id,
                    subscription_id=subscription.id,
                    event_name=payload.event_name,
                    payload_json=payload.payload,
                    target_ref=subscription.target_ref,
                )
                status_value = "queued"
                attempt_count = 0
                delivered_at = None
                error_text = "queued for durable delivery worker"
            record = DeliveryRecord(
                channel_id=channel.id,
                subscription_id=subscription.id,
                event_name=payload.event_name,
                status=status_value,
                attempt_count=attempt_count,
                delivered_at=delivered_at,
                error_text=error_text,
                payload_json=payload.payload,
            )
            db.add(record)
            deliveries.append(record)

        deliveries.extend(await process_due_webhook_jobs(db, channel_id=channel.id))

        if not subscriptions:
            record = DeliveryRecord(
                channel_id=channel.id,
                subscription_id=None,
                event_name=payload.event_name,
                status="no_subscribers",
                attempt_count=0,
                delivered_at=None,
                error_text="",
                payload_json=payload.payload,
            )
            db.add(record)
            deliveries.append(record)
        await db.flush()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.EVENTS.value,
            metric_key="publish_event",
        )
        await db.commit()
        return [
            DeliveryRead(
                id=row.id,
                channel_id=row.channel_id,
                subscription_id=row.subscription_id,
                event_name=row.event_name,
                status=row.status,
                attempt_count=row.attempt_count,
                delivered_at=row.delivered_at,
                error_text=row.error_text,
                payload_json=row.payload_json,
            )
            for row in deliveries
        ]
