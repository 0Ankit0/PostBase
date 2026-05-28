import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("TESTING", "True")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
os.environ.setdefault("POSTGRES_DB", "postbase_test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postbase_test",
)
os.environ.setdefault(
    "SYNC_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postbase_test",
)

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from src.apps.iam.casbin_enforcer import CasbinEnforcer
from src.db import session as db_session_module
from src.db.session import get_session
from src.main import app
from src.postbase import bootstrap_postbase_runtime
from src.postbase.platform.seeding import seed_provider_catalog

TEST_DB_HOST = os.environ["POSTGRES_SERVER"]
TEST_DB_USER = os.environ["POSTGRES_USER"]
TEST_DB_PASSWORD = os.environ["POSTGRES_PASSWORD"]
TEST_DB_NAME = os.environ["POSTGRES_DB"]
TEST_DATABASE_URL = os.environ["DATABASE_URL"]
TEST_DB_PORT = make_url(TEST_DATABASE_URL).port or 5432


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _import_models() -> None:
    import src.apps.core.models  # noqa: F401
    import src.apps.finance.models  # noqa: F401
    import src.apps.iam.models  # noqa: F401
    import src.apps.multitenancy.models  # noqa: F401
    import src.apps.notification.models  # noqa: F401
    import src.apps.observability.models  # noqa: F401
    import src.apps.websocket.models  # noqa: F401
    import src.postbase.domain.models  # noqa: F401


async def _connect_admin(database: str = "postgres") -> asyncpg.Connection:
    try:
        return await asyncpg.connect(
            host=TEST_DB_HOST,
            port=TEST_DB_PORT,
            user=TEST_DB_USER,
            password=TEST_DB_PASSWORD,
            database=database,
        )
    except OSError as exc:
        raise RuntimeError(
            "PostgreSQL is required for backend tests. Start it with "
            "'podman compose up -d db redis' or run 'make bootstrap-local'."
        ) from exc


async def _ensure_test_database() -> None:
    admin = await _connect_admin()
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            TEST_DB_NAME,
        )
        if not exists:
            await admin.execute(f"CREATE DATABASE {_quote_identifier(TEST_DB_NAME)}")
    finally:
        await admin.close()


async def _reset_test_database() -> None:
    connection = await _connect_admin(TEST_DB_NAME)
    try:
        schema_rows = await connection.fetch(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT LIKE 'pg_%'
              AND schema_name <> 'information_schema'
            """
        )
        for row in schema_rows:
            await connection.execute(
                f"DROP SCHEMA IF EXISTS {_quote_identifier(row['schema_name'])} CASCADE"
            )
        await connection.execute("CREATE SCHEMA public")
        await connection.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER")
        await connection.execute("GRANT ALL ON SCHEMA public TO PUBLIC")
    finally:
        await connection.close()


@pytest.fixture(scope="function")
async def test_engine():
    """Create a fresh PostgreSQL-backed test engine for each test."""
    await _ensure_test_database()
    await _reset_test_database()
    _import_models()

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    await engine.dispose()
    await _reset_test_database()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession, test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override and disabled rate limiting."""
    from src.apps.analytics.dependencies import get_analytics
    from src.apps.analytics.service import AnalyticsService
    from src.apps.iam.api.deps import get_db

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    _noop_analytics = AnalyticsService(provider=None)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session] = override_get_db
    app.dependency_overrides[get_analytics] = lambda: _noop_analytics

    original_async_session_factory = db_session_module.async_session_factory
    test_async_session = async_sessionmaker(
        db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    db_session_module.async_session_factory = test_async_session
    bootstrap_postbase_runtime()
    CasbinEnforcer.reset()
    app.state.casbin_enforcer = await CasbinEnforcer.get_enforcer(test_engine)
    await seed_provider_catalog(db_session)

    if hasattr(app.state, "limiter"):
        original_enabled = app.state.limiter.enabled
        app.state.limiter.enabled = False
    else:
        original_enabled = None

    limiters_to_restore = []
    try:
        from src.apps.iam.api.v1.auth import login, password, signup

        for module in [signup, login, password]:
            if hasattr(module, "limiter"):
                limiters_to_restore.append((module.limiter, module.limiter.enabled))
                module.limiter.enabled = False
    except Exception:
        pass

    with patch(
        "src.apps.iam.services.email.EmailService.send_welcome_email",
        new_callable=AsyncMock,
    ):
        with patch(
            "src.apps.iam.services.email.EmailService.send_verification_email",
            new_callable=AsyncMock,
        ):
            with patch(
                "src.apps.iam.services.email.EmailService.send_password_reset_email",
                new_callable=AsyncMock,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as test_client:
                    yield test_client

    if original_enabled is not None:
        app.state.limiter.enabled = original_enabled

    for limiter, was_enabled in limiters_to_restore:
        limiter.enabled = was_enabled

    CasbinEnforcer.reset()
    db_session_module.async_session_factory = original_async_session_factory
    app.dependency_overrides.clear()
