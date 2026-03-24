from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.apps.core.config import settings
from src.apps.core.security import ALGORITHM
from src.postbase.domain.enums import ApiKeyRole
from src.postbase.domain.models import Environment, EnvironmentApiKey, Project, SessionRecord
from src.postbase.platform.security import generate_api_key_material, hash_secret


SAFE_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class PostBaseAccessContext:
    def __init__(
        self,
        *,
        environment: Environment,
        project: Project,
        role: ApiKeyRole | None = None,
        auth_user_id: int | None = None,
        session_id: int | None = None,
        token_type: str = "api_key",
    ) -> None:
        self.environment = environment
        self.project = project
        self.role = role
        self.auth_user_id = auth_user_id
        self.session_id = session_id
        self.token_type = token_type

    @property
    def environment_id(self) -> int:
        return self.environment.id

    @property
    def project_id(self) -> int:
        return self.project.id

    @property
    def service_role(self) -> bool:
        return self.role == ApiKeyRole.SERVICE_ROLE

    @property
    def authenticated(self) -> bool:
        return self.auth_user_id is not None or self.service_role


def validate_identifier(value: str, field_name: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if not SAFE_IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must start with a letter and contain only lowercase letters, digits, and underscores")
    return normalized


def build_physical_schema(project_slug: str, environment_slug: str, namespace: str) -> str:
    raw = f"pb_{project_slug}_{environment_slug}_{namespace}".replace("-", "_").lower()
    raw = re.sub(r"[^a-z0-9_]", "_", raw)
    return raw[:63]


async def issue_environment_api_key(
    db: AsyncSession,
    *,
    environment_id: int,
    name: str,
    role: ApiKeyRole,
) -> tuple[EnvironmentApiKey, str]:
    prefix, secret, full_key = generate_api_key_material()
    api_key = EnvironmentApiKey(
        environment_id=environment_id,
        name=name,
        role=role,
        key_prefix=prefix,
        hashed_secret=hash_secret(secret),
    )
    db.add(api_key)
    await db.flush()
    return api_key, full_key


async def resolve_api_key_context(
    db: AsyncSession,
    api_key_value: str,
) -> PostBaseAccessContext | None:
    if "." not in api_key_value:
        return None

    prefix_part, secret = api_key_value.split(".", 1)
    prefix = prefix_part.removeprefix("pbk_")
    api_key = (
        await db.execute(
            select(EnvironmentApiKey).where(
                EnvironmentApiKey.key_prefix == prefix,
                EnvironmentApiKey.is_active == True,
            )
        )
    ).scalars().first()
    if api_key is None or api_key.hashed_secret != hash_secret(secret):
        return None

    environment = await db.get(Environment, api_key.environment_id)
    if environment is None:
        return None
    project = await db.get(Project, environment.project_id)
    if project is None:
        return None

    api_key.last_used_at = datetime.now(timezone.utc)
    await db.flush()
    return PostBaseAccessContext(
        environment=environment,
        project=project,
        role=api_key.role,
        token_type="api_key",
    )


def create_postbase_access_token(
    *,
    auth_user_id: int,
    project_id: int,
    environment_id: int,
    session_id: int,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    jti = hash_secret(f"access:{auth_user_id}:{session_id}:{expire.timestamp()}")[:32]
    payload: dict[str, Any] = {
        "exp": expire,
        "sub": str(auth_user_id),
        "type": "postbase_access",
        "jti": jti,
        "project_id": project_id,
        "environment_id": environment_id,
        "session_id": session_id,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM), jti


def create_postbase_refresh_token(
    *,
    auth_user_id: int,
    project_id: int,
    environment_id: int,
    session_id: int,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    jti = hash_secret(f"refresh:{auth_user_id}:{session_id}:{expire.timestamp()}")[:32]
    payload: dict[str, Any] = {
        "exp": expire,
        "sub": str(auth_user_id),
        "type": "postbase_refresh",
        "jti": jti,
        "project_id": project_id,
        "environment_id": environment_id,
        "session_id": session_id,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM), jti, expire


def verify_postbase_token(token: str, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise JWTError("Invalid token type")
    return payload


async def resolve_access_context_from_token(
    db: AsyncSession,
    token: str,
) -> PostBaseAccessContext | None:
    try:
        payload = verify_postbase_token(token, "postbase_access")
    except JWTError:
        return None

    session_record = (
        await db.execute(
            select(SessionRecord).where(
                SessionRecord.id == int(payload["session_id"]),
                SessionRecord.access_jti == payload["jti"],
                SessionRecord.revoked_at.is_(None),
            )
        )
    ).scalars().first()
    if session_record is None:
        return None

    environment = await db.get(Environment, int(payload["environment_id"]))
    if environment is None:
        return None
    project = await db.get(Project, environment.project_id)
    if project is None:
        return None

    session_record.last_seen_at = datetime.now(timezone.utc)
    await db.flush()
    return PostBaseAccessContext(
        environment=environment,
        project=project,
        auth_user_id=int(payload["sub"]),
        session_id=session_record.id,
        token_type="jwt",
    )
