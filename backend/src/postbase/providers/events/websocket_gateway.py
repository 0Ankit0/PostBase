from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.config import settings
from src.apps.websocket.manager import manager as ws_manager
from src.postbase.capabilities.events.contracts import (
    ChannelCreateRequest,
    ChannelRead,
    DeliveryRead,
    EventPublishRequest,
    SubscriptionCreateRequest,
    SubscriptionRead,
)
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import DeliveryRecord, EventChannel, Subscription
from src.postbase.platform.access import validate_identifier
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


class WebsocketGatewayEventsProvider:
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.EVENTS,
            provider_key="websocket-gateway",
            supported_operations=["channels", "subscriptions", "publish"],
            optional_features=["room-delivery", "presence"],
            limits={"max_room_name_length": 80},
        )

    async def health(self) -> ProviderHealth:
        detail = f"feature_websockets={settings.FEATURE_WEBSOCKETS} active_connections={ws_manager.total_connections}"
        return ProviderHealth(ready=settings.FEATURE_WEBSOCKETS, detail=detail)

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

    async def list_channels(self, context) -> list[ChannelRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        rows = (
            await db.execute(select(EventChannel).where(EventChannel.environment_id == context.environment_id))
        ).scalars().all()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.EVENTS.value,
            metric_key="list_channels",
        )
        return [ChannelRead(id=row.id, channel_key=row.channel_key, description=row.description) for row in rows]

    async def create_subscription(self, context, channel_id: int, payload: SubscriptionCreateRequest) -> SubscriptionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await db.get(EventChannel, channel_id)
        if channel is None or channel.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        row = Subscription(
            channel_id=channel.id,
            target_type=payload.target_type,
            target_ref=payload.target_ref,
            config_json={**payload.config_json, "provider": "websocket-gateway"},
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
            if subscription.target_type == "room":
                await ws_manager.push_event_to_room(
                    subscription.target_ref,
                    payload.event_name,
                    payload.payload,
                )
            record = DeliveryRecord(
                channel_id=channel.id,
                subscription_id=subscription.id,
                event_name=payload.event_name,
                status=status_value,
                payload_json=payload.payload,
            )
            db.add(record)
            deliveries.append(record)
        if not subscriptions:
            record = DeliveryRecord(
                channel_id=channel.id,
                subscription_id=None,
                event_name=payload.event_name,
                status="no_subscribers",
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
                payload_json=row.payload_json,
            )
            for row in deliveries
        ]
