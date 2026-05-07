from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import DateTime, event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel import SQLModel
from src.apps.core.config import settings
from src.apps.core.settings_store import sync_general_settings

if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the configuration")

engine_kwargs: dict[str, object] = {
    "url": settings.DATABASE_URL,
    "echo": settings.LOG_SQL_QUERIES,
    "future": True,
    "poolclass": AsyncAdaptedQueuePool,
    "pool_size": settings.DB_POOL_SIZE,
    "max_overflow": settings.DB_MAX_OVERFLOW,
    "pool_timeout": settings.DB_POOL_TIMEOUT,
    "pool_recycle": settings.DB_POOL_RECYCLE,
}

engine = create_async_engine(**engine_kwargs)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


def _coerce_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_execution_parameters(value):
    if isinstance(value, datetime):
        return _coerce_naive_utc(value)
    if isinstance(value, tuple):
        return tuple(_normalize_execution_parameters(item) for item in value)
    if isinstance(value, list):
        return [_normalize_execution_parameters(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _normalize_execution_parameters(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_execution_parameters(item) for item in value]
    return value


@event.listens_for(Session, "before_flush")
def _normalize_naive_datetime_columns(session, flush_context, instances) -> None:
    for obj in session.new.union(session.dirty):
        mapper = inspect(obj).mapper
        for attr in mapper.column_attrs:
            column = attr.columns[0]
            if not isinstance(column.type, DateTime) or column.type.timezone:
                continue
            value = getattr(obj, attr.key, None)
            if isinstance(value, datetime) and value.tzinfo is not None:
                setattr(obj, attr.key, _coerce_naive_utc(value))


@event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
def _normalize_datetime_bind_params(conn, cursor, statement, parameters, context, executemany):
    return statement, _normalize_execution_parameters(parameters)

async def init_db():
    # Import all models so SQLModel.metadata knows about every table
    import src.apps.core.models  # noqa: F401
    import src.apps.iam.models  # noqa: F401
    import src.apps.notification.models  # noqa: F401
    import src.apps.multitenancy.models  # noqa: F401
    import src.apps.finance.models  # noqa: F401
    import src.apps.websocket.models  # noqa: F401
    import src.apps.observability.models  # noqa: F401
    import src.postbase.domain.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session_factory() as session:
        await sync_general_settings(session)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
