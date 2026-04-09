from __future__ import annotations

from src.postbase.capabilities.facade_base import CapabilityFacadeBase
from src.postbase.domain.enums import CapabilityKey


class EventsFacade(CapabilityFacadeBase):
    capability = CapabilityKey.EVENTS
