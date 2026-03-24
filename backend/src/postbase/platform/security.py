from __future__ import annotations

import hashlib
import secrets


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_api_key_material() -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    prefix = secrets.token_hex(6)
    full_key = f"pbk_{prefix}.{secret}"
    return prefix, secret, full_key
