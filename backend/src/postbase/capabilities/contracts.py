from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, PlainSerializer, model_validator


def _serialize_iso_datetime(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

ISODateTime = Annotated[
    datetime,
    PlainSerializer(_serialize_iso_datetime, return_type=str),
]


class PostBaseContractModel(BaseModel):
    model_config = {"from_attributes": True}


class ErrorDetail(PostBaseContractModel):
    field: str | None = None
    message: str
    context: dict[str, Any] | None = None


class ErrorEnvelope(PostBaseContractModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(PostBaseContractModel):
    error: ErrorEnvelope

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_shape(cls, value: Any) -> Any:
        if isinstance(value, dict) and "error" not in value and "detail" in value:
            detail = value.get("detail")
            if isinstance(detail, str):
                return {"error": {"code": "legacy_error", "message": detail, "details": []}}
            if isinstance(detail, dict):
                return {
                    "error": {
                        "code": str(detail.get("code", "legacy_error")),
                        "message": str(detail.get("message", "Request failed")),
                        "details": detail.get("details", []),
                    }
                }
        return value


CAPABILITY_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Validation or request error"},
    403: {"model": ErrorResponse, "description": "Permission denied"},
    409: {"model": ErrorResponse, "description": "Conflict"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
    502: {"model": ErrorResponse, "description": "Provider failure"},
}


class FacadeStatusResponse(PostBaseContractModel):
    status: Literal["ready", "degraded", "error"]
    reason: str
    provider_key: str | None = None
