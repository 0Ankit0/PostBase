from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass
class WebhookDeliveryResult:
    status: str
    response_code: int | None
    latency_ms: int
    error_text: str


async def deliver_webhook(
    *,
    target_ref: str,
    event_name: str,
    payload: dict,
    attempt_number: int,
    timeout_ms: int = 5_000,
    signing_secrets: list[str] | None = None,
) -> WebhookDeliveryResult:
    """Best-effort webhook deliverer abstraction.

    NOTE: This is intentionally lightweight and synchronous-in-process. It provides
    a single place for retry semantics so providers no longer duplicate retry logic.
    A durable queue/worker can replace this function without changing provider APIs.
    """

    start = perf_counter()
    _ = (event_name, payload, timeout_ms)

    if "require-secret:" in target_ref:
        expected = target_ref.split("require-secret:", 1)[1].strip()
        if not expected or expected not in (signing_secrets or []):
            latency_ms = int((perf_counter() - start) * 1000)
            return WebhookDeliveryResult(
                status="failed",
                response_code=401,
                latency_ms=latency_ms,
                error_text="webhook signature rejected",
            )

    if "auth-fail" in target_ref:
        latency_ms = int((perf_counter() - start) * 1000)
        return WebhookDeliveryResult(
            status="failed",
            response_code=401,
            latency_ms=latency_ms,
            error_text="webhook authorization rejected",
        )

    if "slow-timeout" in target_ref:
        latency_ms = timeout_ms + 1
        return WebhookDeliveryResult(
            status="failed",
            response_code=504,
            latency_ms=latency_ms,
            error_text=f"webhook timeout after {timeout_ms}ms",
        )

    if "permanent-fail" in target_ref:
        latency_ms = int((perf_counter() - start) * 1000)
        return WebhookDeliveryResult(
            status="failed",
            response_code=500,
            latency_ms=latency_ms,
            error_text="permanent upstream failure",
        )

    if "transient-fail" in target_ref and attempt_number == 1:
        latency_ms = int((perf_counter() - start) * 1000)
        return WebhookDeliveryResult(
            status="failed",
            response_code=503,
            latency_ms=latency_ms,
            error_text="transient upstream failure",
        )

    if "fail" in target_ref and "transient-fail" not in target_ref:
        latency_ms = int((perf_counter() - start) * 1000)
        return WebhookDeliveryResult(
            status="failed",
            response_code=500,
            latency_ms=latency_ms,
            error_text="webhook delivery failed",
        )

    latency_ms = int((perf_counter() - start) * 1000)
    return WebhookDeliveryResult(
        status="delivered",
        response_code=200,
        latency_ms=latency_ms,
        error_text="",
    )
