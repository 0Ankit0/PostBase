from datetime import datetime, timezone

from src.postbase.capabilities.contracts import ErrorResponse
from src.postbase.capabilities.events.contracts import DeliveryRead
from src.postbase.capabilities.functions.contracts import ExecutionRead, FunctionCreateRequest


def test_capability_contract_timestamp_serialization_uses_utc_z_suffix() -> None:
    execution = ExecutionRead(
        id=1,
        function_definition_id=2,
        invocation_type="sync",
        idempotency_key=None,
        correlation_id="corr-1",
        replay_of_execution_id=None,
        retry_of_execution_id=None,
        retry_count=0,
        timeout_ms=None,
        cancel_requested=False,
        schedule_id=None,
        trigger_source="api",
        execution_metadata_json={},
        status="completed",
        input_json={"hello": "world"},
        output_json={"ok": True},
        started_at=datetime(2026, 4, 1, 12, 30, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 1, 12, 31, tzinfo=timezone.utc),
    )
    payload = execution.model_dump(mode="json")
    assert payload["started_at"] == "2026-04-01T12:30:00Z"
    assert payload["completed_at"] == "2026-04-01T12:31:00Z"

    delivery = DeliveryRead(
        id=3,
        channel_id=4,
        subscription_id=None,
        event_name="deploy.complete",
        status="queued",
        attempt_count=0,
        delivered_at=None,
        payload_json={"version": "1.2.3"},
    )
    delivery_payload = delivery.model_dump(mode="json")
    assert delivery_payload["delivered_at"] is None
    assert delivery_payload["error_text"] == ""


def test_error_response_accepts_legacy_and_new_shapes() -> None:
    legacy_string = ErrorResponse.model_validate({"detail": "Channel not found"})
    assert legacy_string.error.code == "legacy_error"
    assert legacy_string.error.message == "Channel not found"

    legacy_dict = ErrorResponse.model_validate(
        {
            "detail": {
                "code": "binding_active_uniqueness_conflict",
                "message": "active_binding_conflict",
            }
        }
    )
    assert legacy_dict.error.code == "binding_active_uniqueness_conflict"
    assert legacy_dict.error.message == "active_binding_conflict"

    modern = ErrorResponse.model_validate(
        {
            "error": {
                "code": "provider_failure",
                "message": "Provider unavailable",
                "details": [{"field": "provider_key", "message": "timed out"}],
            }
        }
    )
    assert modern.error.details[0].field == "provider_key"


def test_function_create_request_backward_compatible_defaults() -> None:
    request = FunctionCreateRequest.model_validate({"slug": "echo", "name": "Echo"})
    assert request.handler_type == "echo"
    assert request.runtime_profile == "celery-runtime"
    assert request.config_json == {}
