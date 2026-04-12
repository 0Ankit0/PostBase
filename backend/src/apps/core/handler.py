import asyncio
import logging

from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from fastapi import Request

from src.db import session as db_session_module
from src.apps.observability.service import record_rate_limit_event

log = logging.getLogger(__name__)


def rate_limit_exceeded_handler(request: Request, exc: Exception):
    if isinstance(exc, RateLimitExceeded):
        async def _persist_rate_limit_event() -> None:
            try:
                async with db_session_module.async_session_factory() as session:
                    await record_rate_limit_event(session, request=request, detail=str(exc))
                    await session.commit()
            except Exception as persist_error:
                log.exception(
                    "Failed to persist rate limit event",
                    extra={
                        "event_code": "ops.rate_limit_persist_failed",
                        "path": request.url.path,
                        "method": request.method,
                        "error_type": type(persist_error).__name__,
                    },
                )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist_rate_limit_event())
        except RuntimeError as loop_error:
            log.warning(
                "No running event loop available for rate limit persistence",
                extra={
                    "event_code": "ops.rate_limit_persist_skipped",
                    "path": request.url.path,
                    "method": request.method,
                    "error_type": type(loop_error).__name__,
                },
            )
        return _rate_limit_exceeded_handler(request, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
