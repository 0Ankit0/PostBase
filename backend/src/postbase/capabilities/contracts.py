from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FacadeStatusResponse(BaseModel):
    status: Literal["ready", "degraded", "error"]
    reason: str
    provider_key: str | None = None
