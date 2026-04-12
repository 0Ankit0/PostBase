from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.config import settings
from src.apps.core.schemas import PaginatedResponse
from src.apps.websocket.manager import manager as ws_manager
from src.postbase.capabilities.events.contracts import (
    ChannelCreateRequest,
    ChannelRead,
    ChannelUpdateRequest,
    DeliveryRead,
    EventPublishRequest,
    SubscriptionCreateRequest,
    SubscriptionRead,
    SubscriptionUpdateRequest,
    WebhookEndpointRead,
    WebhookSecretRotateRequest,
)
from src.postbase.capabilities.events.policy import authorize_channel_operation, resolve_policy_template
from src.postbase.capabilities.events.validation import validate_subscription_configuration
from src.postbase.capabilities.events.webhook_jobs import enqueue_webhook_job, process_due_webhook_jobs
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import DeliveryRecord, EventChannel, Subscription
from src.postbase.platform.access import validate_identifier
from src.postbase.platform.audit import record_channel_policy_event, record_webhook_secret_rotation_event
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
            policy_json=resolve_policy_template(payload.policy_template),
        )
        db.add(row)
        await db.flush()
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.EVENTS.value, metric_key="create_channel")
        await db.commit()
        return ChannelRead(id=row.id, channel_key=row.channel_key, description=row.description, policy_json=row.policy_json)

    async def list_channels(self, context, *, skip: int, limit: int) -> PaginatedResponse[ChannelRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        total = (await db.execute(select(func.count()).select_from(EventChannel).where(EventChannel.environment_id == context.environment_id))).scalar_one()
        rows = (
            await db.execute(
                select(EventChannel).where(EventChannel.environment_id == context.environment_id).order_by(EventChannel.id.desc()).offset(skip).limit(limit)
            )
        ).scalars().all()
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.EVENTS.value, metric_key="list_channels")
        return PaginatedResponse[ChannelRead].create(
            items=[ChannelRead(id=row.id, channel_key=row.channel_key, description=row.description, policy_json=row.policy_json) for row in rows],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def get_channel(self, context, channel_id: int) -> ChannelRead:
        channel = await self._get_channel(context, channel_id)
        return ChannelRead(id=channel.id, channel_key=channel.channel_key, description=channel.description, policy_json=channel.policy_json)

    async def update_channel(self, context, channel_id: int, payload: ChannelUpdateRequest) -> ChannelRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await self._get_channel(context, channel_id)
        previous_policy = dict(channel.policy_json or {})
        if payload.description is not None:
            channel.description = payload.description
        if payload.policy_template:
            channel.policy_json = resolve_policy_template(payload.policy_template)
        elif payload.policy_json is not None:
            channel.policy_json = payload.policy_json
        await db.flush()
        if previous_policy != channel.policy_json:
            await record_channel_policy_event(db, context=context, channel_id=channel.id, channel_key=channel.channel_key, previous_policy=previous_policy, next_policy=channel.policy_json)
        await db.commit()
        return ChannelRead(id=channel.id, channel_key=channel.channel_key, description=channel.description, policy_json=channel.policy_json)

    async def delete_channel(self, context, channel_id: int) -> None:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await self._get_channel(context, channel_id)
        await db.delete(channel)
        await db.commit()

    async def create_subscription(self, context, channel_id: int, payload: SubscriptionCreateRequest) -> SubscriptionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await self._get_channel(context, channel_id)
        self._authorize(context, channel, "subscribe")
        payload = validate_subscription_configuration(context, payload)
        row = Subscription(channel_id=channel.id, target_type=payload.target_type, target_ref=payload.target_ref, config_json={**payload.config_json, "provider": "websocket-gateway"})
        db.add(row)
        await db.flush()
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.EVENTS.value, metric_key="create_subscription")
        await db.commit()
        return self._subscription_read(row)

    async def update_subscription(self, context, subscription_id: int, payload: SubscriptionUpdateRequest) -> SubscriptionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await db.get(Subscription, subscription_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        channel = await self._get_channel(context, row.channel_id)
        self._authorize(context, channel, "subscribe")

        next_payload = SubscriptionCreateRequest(target_type=payload.target_type or row.target_type, target_ref=payload.target_ref or row.target_ref, config_json={**row.config_json, **(payload.config_json or {})})
        validated = validate_subscription_configuration(context, next_payload)
        row.target_type = validated.target_type
        row.target_ref = validated.target_ref
        row.config_json = validated.config_json
        if payload.is_active is not None:
            row.is_active = payload.is_active

        await db.flush()
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.EVENTS.value, metric_key="update_subscription")
        await db.commit()
        return self._subscription_read(row)

    async def publish(self, context, channel_id: int, payload: EventPublishRequest) -> list[DeliveryRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await self._get_channel(context, channel_id)
        self._authorize(context, channel, "publish")
        subscriptions = (await db.execute(select(Subscription).where(Subscription.channel_id == channel.id, Subscription.is_active == True))).scalars().all()
        deliveries: list[DeliveryRecord] = []
        for subscription in subscriptions:
            status_value = "delivered"
            attempt_count = 1
            delivered_at = datetime.now(timezone.utc)
            error_text = ""
            if subscription.target_type == "room":
                await ws_manager.push_event_to_room(subscription.target_ref, payload.event_name, payload.payload)
            elif subscription.target_type == "webhook":
                await enqueue_webhook_job(
                    db,
                    channel_id=channel.id,
                    subscription_id=subscription.id,
                    event_name=payload.event_name,
                    payload_json=payload.payload,
                    target_ref=subscription.target_ref,
                    signing_secrets=_resolve_signing_secrets(subscription),
                )
                status_value = "queued"
                attempt_count = 0
                delivered_at = None
                error_text = "queued for durable delivery worker"
            record = DeliveryRecord(channel_id=channel.id, subscription_id=subscription.id, event_name=payload.event_name, status=status_value, attempt_count=attempt_count, delivered_at=delivered_at, error_text=error_text, payload_json=payload.payload)
            db.add(record)
            deliveries.append(record)

        deliveries.extend(await process_due_webhook_jobs(db, channel_id=channel.id))

        if not subscriptions:
            record = DeliveryRecord(channel_id=channel.id, subscription_id=None, event_name=payload.event_name, status="no_subscribers", attempt_count=0, delivered_at=None, error_text="", payload_json=payload.payload)
            db.add(record)
            deliveries.append(record)
        await db.flush()
        await record_usage(db, environment_id=context.environment_id, capability_key=CapabilityKey.EVENTS.value, metric_key="publish_event")
        await db.commit()
        return [DeliveryRead(id=row.id, channel_id=row.channel_id, subscription_id=row.subscription_id, event_name=row.event_name, status=row.status, attempt_count=row.attempt_count, delivered_at=row.delivered_at, error_text=row.error_text, payload_json=row.payload_json) for row in deliveries]

    async def list_webhook_endpoints(self, context, *, channel_id: int | None, skip: int, limit: int) -> PaginatedResponse[WebhookEndpointRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        filters = [Subscription.target_type == "webhook"]
        if channel_id is not None:
            channel = await self._get_channel(context, channel_id)
            filters.append(Subscription.channel_id == channel.id)
        else:
            rows = (await db.execute(select(EventChannel.id).where(EventChannel.environment_id == context.environment_id))).scalars().all()
            if not rows:
                return PaginatedResponse[WebhookEndpointRead].create(items=[], total=0, skip=skip, limit=limit)
            filters.append(Subscription.channel_id.in_(rows))
        total = (await db.execute(select(func.count()).select_from(Subscription).where(*filters))).scalar_one()
        subscriptions = (await db.execute(select(Subscription).where(*filters).order_by(Subscription.id.desc()).offset(skip).limit(limit))).scalars().all()
        return PaginatedResponse[WebhookEndpointRead].create(items=[_to_webhook_endpoint_read(item) for item in subscriptions], total=total, skip=skip, limit=limit)

    async def rotate_webhook_secret(self, context, subscription_id: int, payload: WebhookSecretRotateRequest) -> WebhookEndpointRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        row = await db.get(Subscription, subscription_id)
        if row is None or row.target_type != "webhook":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found")
        channel = await self._get_channel(context, row.channel_id)
        self._authorize(context, channel, "manage")
        now = datetime.now(timezone.utc)
        secrets = row.config_json.get("endpoint_secrets") or {}
        current_secret = str(secrets.get("active") or "")
        previous_secret = current_secret if current_secret else None
        row.config_json = {
            **row.config_json,
            "endpoint_secrets": {
                "active": payload.new_secret,
                "previous": previous_secret,
                "previous_expires_at": (now + timedelta(seconds=payload.grace_window_seconds)).isoformat() if previous_secret else None,
            },
        }
        await db.flush()
        await record_webhook_secret_rotation_event(db, context=context, channel_id=channel.id, subscription_id=row.id, grace_window_seconds=payload.grace_window_seconds)
        await db.commit()
        return _to_webhook_endpoint_read(row)

    async def _get_channel(self, context, channel_id: int) -> EventChannel:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        channel = await db.get(EventChannel, channel_id)
        if channel is None or channel.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        return channel

    def _authorize(self, context, channel: EventChannel, operation: str) -> None:
        decision = authorize_channel_operation(context, policy_json=channel.policy_json or resolve_policy_template("open"), operation=operation)
        if not decision.allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)

    def _subscription_read(self, row: Subscription) -> SubscriptionRead:
        return SubscriptionRead(id=row.id, channel_id=row.channel_id, target_type=row.target_type, target_ref=row.target_ref, config_json=row.config_json, is_active=row.is_active)


def _resolve_signing_secrets(subscription: Subscription) -> list[str]:
    endpoint_secrets = (subscription.config_json or {}).get("endpoint_secrets") or {}
    now = datetime.now(timezone.utc)
    active = endpoint_secrets.get("active")
    previous = endpoint_secrets.get("previous")
    previous_expires_at = endpoint_secrets.get("previous_expires_at")
    secrets: list[str] = []
    if isinstance(active, str) and active:
        secrets.append(active)
    if isinstance(previous, str) and previous:
        if previous_expires_at:
            try:
                expires_at = datetime.fromisoformat(str(previous_expires_at))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if now <= expires_at:
                    secrets.append(previous)
            except ValueError:
                secrets.append(previous)
    return secrets


def _to_webhook_endpoint_read(row: Subscription) -> WebhookEndpointRead:
    endpoint_secrets = (row.config_json or {}).get("endpoint_secrets") or {}
    return WebhookEndpointRead(
        id=row.id,
        channel_id=row.channel_id,
        target_ref=row.target_ref,
        is_active=row.is_active,
        has_active_secret=bool(endpoint_secrets.get("active")),
        has_previous_secret=bool(endpoint_secrets.get("previous")),
        previous_secret_expires_at=endpoint_secrets.get("previous_expires_at"),
    )
