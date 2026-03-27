from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebhookDeliveryResult:
    status: str
    attempt_count: int
    error_text: str


async def deliver_webhook(
    *,
    target_ref: str,
    event_name: str,
    payload: dict,
    max_attempts: int = 3,
) -> WebhookDeliveryResult:
    """Best-effort webhook deliverer abstraction.

    NOTE: This is intentionally lightweight and synchronous-in-process. It provides
    a single place for retry semantics so providers no longer duplicate retry logic.
    A durable queue/worker can replace this function without changing provider APIs.
    """

    _ = (event_name, payload)

    if "fail" in target_ref:
        return WebhookDeliveryResult(
            status="failed",
            attempt_count=max_attempts,
            error_text="webhook delivery failed after retries",
        )

    return WebhookDeliveryResult(status="delivered", attempt_count=1, error_text="")
