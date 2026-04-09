from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, status

from src.postbase.capabilities.events.contracts import SubscriptionCreateRequest
from src.postbase.platform.access import validate_identifier

_ALLOWED_SIGNATURE_ALGORITHMS = {"sha256", "sha512"}


def validate_subscription_configuration(context, payload: SubscriptionCreateRequest) -> SubscriptionCreateRequest:
    tenant_scope = payload.config_json.get("tenant_id")
    if tenant_scope is not None:
        try:
            tenant_scope_id = int(tenant_scope)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="config_json.tenant_id must be an integer when provided",
            ) from exc
        if tenant_scope_id != context.project.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cross-tenant subscriptions are not allowed",
            )

    target_ref = payload.target_ref.strip()
    if payload.target_type == "room":
        room_name = validate_identifier(target_ref, "Room name")
        if len(room_name) > 80:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room name must be 80 characters or fewer",
            )
        return SubscriptionCreateRequest(
            target_type="room",
            target_ref=room_name,
            config_json=payload.config_json,
        )

    endpoint = urlparse(target_ref)
    if endpoint.scheme != "https" or not endpoint.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook subscriptions require an HTTPS endpoint",
        )

    signature = payload.config_json.get("signature")
    if not isinstance(signature, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook subscriptions require config_json.signature settings",
        )
    secret_ref = signature.get("secret_ref")
    if not isinstance(secret_ref, str) or not secret_ref.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signatures require signature.secret_ref",
        )

    algorithm = str(signature.get("algorithm", "sha256")).lower()
    if algorithm not in _ALLOWED_SIGNATURE_ALGORITHMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signatures support only sha256 or sha512 algorithms",
        )

    return SubscriptionCreateRequest(
        target_type="webhook",
        target_ref=target_ref,
        config_json={
            **payload.config_json,
            "signature": {**signature, "algorithm": algorithm},
        },
    )
