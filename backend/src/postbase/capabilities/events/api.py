from fastapi import APIRouter, Depends

from src.postbase.capabilities.events.contracts import (
    ChannelCreateRequest,
    ChannelRead,
    DeliveryRead,
    EventPublishRequest,
    SubscriptionCreateRequest,
    SubscriptionRead,
)
from src.postbase.capabilities.events.dependencies import get_access_context, get_events_provider

router = APIRouter(prefix="/events", tags=["postbase-events"])


@router.post("/channels", response_model=ChannelRead)
async def create_channel(
    payload: ChannelCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> ChannelRead:
    return await provider.create_channel(context, payload)


@router.get("/channels", response_model=list[ChannelRead])
async def list_channels(
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> list[ChannelRead]:
    return await provider.list_channels(context)


@router.post("/subscriptions/{channel_id}", response_model=SubscriptionRead)
async def create_subscription(
    channel_id: int,
    payload: SubscriptionCreateRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> SubscriptionRead:
    return await provider.create_subscription(context, channel_id, payload)


@router.post("/publish/{channel_id}", response_model=list[DeliveryRead])
async def publish_event(
    channel_id: int,
    payload: EventPublishRequest,
    context=Depends(get_access_context),
    provider=Depends(get_events_provider),
) -> list[DeliveryRead]:
    return await provider.publish(context, channel_id, payload)
