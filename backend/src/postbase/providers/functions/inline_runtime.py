from __future__ import annotations

from fastapi import HTTPException, status

from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import FunctionDefinition
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.providers.functions.celery_runtime import CeleryRuntimeFunctionsProvider


class InlineRuntimeFunctionsProvider(CeleryRuntimeFunctionsProvider):
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.FUNCTIONS,
            provider_key="inline-runtime",
            supported_operations=[
                "create",
                "list",
                "invoke",
                "executions",
                "schedules",
                "deployment_history",
                "revisions",
            ],
            optional_features=["sync"],
            limits={"max_payload_bytes": 65536},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(ready=True, detail="inline execution enabled")

    def _execute_handler(
        self,
        function: FunctionDefinition,
        payload: dict,
        context,
        *,
        timeout_ms: int | None = None,
        cancel_requested: bool = False,
    ) -> dict:
        if cancel_requested:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invocation canceled by caller")
        if timeout_ms is not None and int(payload.get("simulate_duration_ms", 0)) > timeout_ms:
            raise TimeoutError("inline runtime adapter timeout exceeded")
        if function.handler_type == "echo":
            return {"echo": payload, "provider": "inline-runtime", "environment_id": context.environment_id}
        if function.handler_type == "template":
            return {"message": function.config_json.get("template", "ok"), "provider": "inline-runtime"}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported handler type")
