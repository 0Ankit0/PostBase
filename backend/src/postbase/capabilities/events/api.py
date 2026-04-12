from fastapi import APIRouter, Depends, Query

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import CAPABILITY_ERROR_RESPONSES, FacadeStatusResponse
from src.postbase.capabilities.events.contracts import (
    ChannelCreateRequest,
    ChannelPermissionCheckRead,
    ChannelRead,
    ChannelUpdateRequest,
    ChannelPolicyTemplateRead,
    DeliveryRead,
    EventPublishRequest,
    SubscriptionCreateRequest,
    SubscriptionRead,
    SubscriptionUpdateRequest,
    WebhookEndpointRead,
    WebhookSecretRotateRequest,
)
from src.postbase.capabilities.events.dependencies import get_access_context, get_events_facade, get_events_provider
from src.postbase.capabilities.events.policy import POLICY_TEMPLATES, authorize_channel_operation
from src.postbase.capabilities.events.service import EventsFacade

router = APIRouter(prefix="/events", tags=["postbase-events"])


@router.get("/channel-policy-templates", response_model=list[ChannelPolicyTemplateRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_channel_policy_templates() -> list[ChannelPolicyTemplateRead]:
    return [
        ChannelPolicyTemplateRead(template_key=key, description=f"{key} template", policy_json=value)
        for key, value in POLICY_TEMPLATES.items()
    ]


@router.post("/channels", response_model=ChannelRead, responses=CAPABILITY_ERROR_RESPONSES)
async def create_channel(
    payload: ChannelCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> ChannelRead:
    return await provider.create_channel(context, payload)


@router.get("/channels", response_model=PaginatedResponse[ChannelRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_channels(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> PaginatedResponse[ChannelRead]:
    return await provider.list_channels(context, skip=skip, limit=limit)


@router.get("/channels/{channel_id}", response_model=ChannelRead, responses=CAPABILITY_ERROR_RESPONSES)
async def get_channel(
    channel_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> ChannelRead:
    return await provider.get_channel(context, channel_id)


@router.patch("/channels/{channel_id}", response_model=ChannelRead, responses=CAPABILITY_ERROR_RESPONSES)
async def update_channel(
    channel_id: int,
    payload: ChannelUpdateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> ChannelRead:
    return await provider.update_channel(context, channel_id, payload)


@router.delete("/channels/{channel_id}", status_code=204, responses=CAPABILITY_ERROR_RESPONSES)
async def delete_channel(
    channel_id: int,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> None:
    await provider.delete_channel(context, channel_id)


@router.get("/channels/{channel_id}/permissions/{operation}", response_model=ChannelPermissionCheckRead, responses=CAPABILITY_ERROR_RESPONSES)
async def check_channel_permission(
    channel_id: int,
    operation: str,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> ChannelPermissionCheckRead:
    channel = await provider.get_channel(context, channel_id)
    decision = authorize_channel_operation(context, policy_json=channel.policy_json, operation=operation)
    return ChannelPermissionCheckRead(operation=operation, allowed=decision.allowed, reason=decision.reason)


@router.post("/subscriptions/{channel_id}", response_model=SubscriptionRead, responses=CAPABILITY_ERROR_RESPONSES)
async def create_subscription(
    channel_id: int,
    payload: SubscriptionCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> SubscriptionRead:
    return await provider.create_subscription(context, channel_id, payload)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionRead, responses=CAPABILITY_ERROR_RESPONSES)
async def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> SubscriptionRead:
    return await provider.update_subscription(context, subscription_id, payload)


@router.get("/webhook-endpoints", response_model=PaginatedResponse[WebhookEndpointRead], responses=CAPABILITY_ERROR_RESPONSES)
async def list_webhook_endpoints(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    channel_id: int | None = Query(default=None),
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> PaginatedResponse[WebhookEndpointRead]:
    return await provider.list_webhook_endpoints(context, channel_id=channel_id, skip=skip, limit=limit)


@router.post("/webhook-endpoints/{subscription_id}/rotate-secret", response_model=WebhookEndpointRead, responses=CAPABILITY_ERROR_RESPONSES)
async def rotate_webhook_secret(
    subscription_id: int,
    payload: WebhookSecretRotateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> WebhookEndpointRead:
    return await provider.rotate_webhook_secret(context, subscription_id, payload)


@router.post("/publish/{channel_id}", response_model=list[DeliveryRead], responses=CAPABILITY_ERROR_RESPONSES)
async def publish_event(
    channel_id: int,
    payload: EventPublishRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> list[DeliveryRead]:
    return await provider.publish(context, channel_id, payload)


@router.get("/status", response_model=FacadeStatusResponse, responses=CAPABILITY_ERROR_RESPONSES)
async def events_status(
    context=Depends(get_access_context),
    facade: EventsFacade = Depends(get_events_facade),
) -> FacadeStatusResponse:
    return await facade.status(context)
