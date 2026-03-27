from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from typing import Literal

from pydantic import BaseModel


class ChannelCreateRequest(BaseModel):
    channel_key: str
    description: str = ""


class ChannelRead(BaseModel):
    id: int
    channel_key: str
    description: str


class SubscriptionCreateRequest(BaseModel):
    target_type: Literal["room", "webhook"]
    target_ref: str
    config_json: dict[str, Any] = {}


class SubscriptionRead(BaseModel):
    id: int
    channel_id: int
    target_type: Literal["room", "webhook"]
    target_ref: str
    config_json: dict[str, Any]
    is_active: bool


class EventPublishRequest(BaseModel):
    event_name: str
    payload: dict[str, Any] = {}


class DeliveryRead(BaseModel):
    id: int
    channel_id: int
    subscription_id: int | None
    event_name: str
    status: str
    attempt_count: int
    delivered_at: datetime | None
    error_text: str
    payload_json: dict[str, Any]


class EventsProvider(Protocol):
    async def create_channel(self, context, payload: ChannelCreateRequest) -> ChannelRead:
        ...

    async def list_channels(self, context) -> list[ChannelRead]:
        ...

    async def create_subscription(self, context, channel_id: int, payload: SubscriptionCreateRequest) -> SubscriptionRead:
        ...

    async def publish(self, context, channel_id: int, payload: EventPublishRequest) -> list[DeliveryRead]:
        ...
