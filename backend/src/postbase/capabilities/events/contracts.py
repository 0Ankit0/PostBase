from __future__ import annotations

from typing import Any, Protocol
from typing import Literal

from pydantic import Field

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import ISODateTime, PostBaseContractModel
from src.postbase.platform.contracts import ProviderAdapter


class ChannelPolicyTemplateRead(PostBaseContractModel):
    template_key: str
    description: str
    policy_json: dict[str, Any] = Field(default_factory=dict)


class ChannelCreateRequest(PostBaseContractModel):
    channel_key: str
    description: str = ""
    policy_template: str = "open"


class ChannelUpdateRequest(PostBaseContractModel):
    description: str | None = None
    policy_json: dict[str, Any] | None = None
    policy_template: str | None = None


class ChannelRead(PostBaseContractModel):
    id: int
    channel_key: str
    description: str
    policy_json: dict[str, Any] = Field(default_factory=dict)


class ChannelPermissionCheckRequest(PostBaseContractModel):
    operation: Literal["manage", "subscribe", "publish", "consume"]


class ChannelPermissionCheckRead(PostBaseContractModel):
    operation: str
    allowed: bool
    reason: str


class SubscriptionCreateRequest(PostBaseContractModel):
    target_type: Literal["room", "webhook"]
    target_ref: str
    config_json: dict[str, Any] = Field(default_factory=dict)


class SubscriptionUpdateRequest(PostBaseContractModel):
    target_type: Literal["room", "webhook"] | None = None
    target_ref: str | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None


class SubscriptionRead(PostBaseContractModel):
    id: int
    channel_id: int
    target_type: Literal["room", "webhook"]
    target_ref: str
    config_json: dict[str, Any]
    is_active: bool


class WebhookSecretRotateRequest(PostBaseContractModel):
    new_secret: str
    grace_window_seconds: int = Field(default=300, ge=60, le=3600)


class WebhookEndpointRead(PostBaseContractModel):
    id: int
    channel_id: int
    target_ref: str
    is_active: bool
    has_active_secret: bool
    has_previous_secret: bool
    previous_secret_expires_at: ISODateTime | None


class EventPublishRequest(PostBaseContractModel):
    event_name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DeliveryRead(PostBaseContractModel):
    id: int
    channel_id: int
    subscription_id: int | None
    event_name: str
    status: str
    attempt_count: int
    delivered_at: ISODateTime | None
    error_text: str = ""
    payload_json: dict[str, Any]


class EventsProvider(ProviderAdapter, Protocol):
    async def create_channel(self, context, payload: ChannelCreateRequest) -> ChannelRead:
        ...

    async def list_channels(self, context, *, skip: int, limit: int) -> PaginatedResponse[ChannelRead]:
        ...

    async def get_channel(self, context, channel_id: int) -> ChannelRead:
        ...

    async def update_channel(self, context, channel_id: int, payload: ChannelUpdateRequest) -> ChannelRead:
        ...

    async def delete_channel(self, context, channel_id: int) -> None:
        ...

    async def create_subscription(self, context, channel_id: int, payload: SubscriptionCreateRequest) -> SubscriptionRead:
        ...

    async def update_subscription(self, context, subscription_id: int, payload: SubscriptionUpdateRequest) -> SubscriptionRead:
        ...

    async def publish(self, context, channel_id: int, payload: EventPublishRequest) -> list[DeliveryRead]:
        ...

    async def list_webhook_endpoints(self, context, *, channel_id: int | None, skip: int, limit: int) -> PaginatedResponse[WebhookEndpointRead]:
        ...

    async def rotate_webhook_secret(self, context, subscription_id: int, payload: WebhookSecretRotateRequest) -> WebhookEndpointRead:
        ...
