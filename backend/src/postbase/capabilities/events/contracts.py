from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from typing import Literal

from pydantic import BaseModel, Field

from src.apps.core.schemas import PaginatedResponse
from src.postbase.platform.contracts import ProviderAdapter


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
    config_json: dict[str, Any] = Field(default_factory=dict)


class SubscriptionUpdateRequest(BaseModel):
    target_type: Literal["room", "webhook"] | None = None
    target_ref: str | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None


class SubscriptionRead(BaseModel):
    id: int
    channel_id: int
    target_type: Literal["room", "webhook"]
    target_ref: str
    config_json: dict[str, Any]
    is_active: bool


class EventPublishRequest(BaseModel):
    event_name: str
    payload: dict[str, Any] = Field(default_factory=dict)


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


class EventsProvider(ProviderAdapter, Protocol):
    async def create_channel(self, context, payload: ChannelCreateRequest) -> ChannelRead:
        ...

    async def list_channels(self, context, *, skip: int, limit: int) -> PaginatedResponse[ChannelRead]:
        ...

    async def create_subscription(self, context, channel_id: int, payload: SubscriptionCreateRequest) -> SubscriptionRead:
        ...

    async def update_subscription(self, context, subscription_id: int, payload: SubscriptionUpdateRequest) -> SubscriptionRead:
        ...

    async def publish(self, context, channel_id: int, payload: EventPublishRequest) -> list[DeliveryRead]:
        ...
