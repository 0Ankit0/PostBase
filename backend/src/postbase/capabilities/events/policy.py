from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status


POLICY_TEMPLATES: dict[str, dict] = {
    "open": {
        "allowed_operations": ["manage", "subscribe", "publish", "consume"],
        "allow_authenticated": True,
    },
    "publish_only": {
        "allowed_operations": ["publish", "consume"],
        "allow_authenticated": True,
    },
    "admin_only": {
        "allowed_operations": ["manage", "subscribe", "publish", "consume"],
        "allow_authenticated": False,
        "allow_service_role": True,
    },
    "read_only": {
        "allowed_operations": ["consume"],
        "allow_authenticated": True,
    },
}


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str


def resolve_policy_template(template_key: str) -> dict:
    policy = POLICY_TEMPLATES.get(template_key)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown policy template '{template_key}'")
    return dict(policy)


def authorize_channel_operation(context, *, policy_json: dict, operation: str) -> PermissionDecision:
    allowed_ops = set(policy_json.get("allowed_operations") or [])
    if operation not in allowed_ops:
        return PermissionDecision(False, f"operation '{operation}' is not permitted by channel policy")

    if context.service_role and policy_json.get("allow_service_role", True):
        return PermissionDecision(True, "service role allowed")

    if context.authenticated and policy_json.get("allow_authenticated", True):
        allowed_user_ids = policy_json.get("allowed_user_ids")
        if isinstance(allowed_user_ids, list) and context.auth_user_id is not None:
            if allowed_user_ids and context.auth_user_id not in allowed_user_ids:
                return PermissionDecision(False, "authenticated user not in channel allow-list")
        return PermissionDecision(True, "authenticated principal allowed")

    return PermissionDecision(False, "channel policy denies principal scope")
