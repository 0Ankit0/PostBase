from fastapi import APIRouter, Depends, Query

from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.contracts import CAPABILITY_ERROR_RESPONSES, FacadeStatusResponse
from src.postbase.capabilities.events.contracts import (
    ChannelCreateRequest,
    ChannelRead,
    DeliveryRead,
    EventPublishRequest,
    SubscriptionCreateRequest,
    SubscriptionRead,
    SubscriptionUpdateRequest,
)
from src.postbase.capabilities.events.dependencies import get_access_context, get_events_facade, get_events_provider
from src.postbase.capabilities.events.service import EventsFacade

router = APIRouter(prefix="/events", tags=["postbase-events"])


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
