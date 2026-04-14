import os
os.environ["TESTING"] = "True"

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from src.apps.iam.casbin_enforcer import CasbinEnforcer
from src.db import session as db_session_module
from src.db.session import get_session
from src.main import app
from src.postbase import bootstrap_postbase_runtime
from src.postbase.platform.seeding import seed_provider_catalog


@pytest.fixture(scope="function")
async def test_engine():
    """Create a test engine for each test function with unique database."""
    # Use in-memory database with StaticPool
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession, test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override and disabled rate limiting."""
    from src.apps.iam.api.deps import get_db
    from src.apps.analytics.service import AnalyticsService
    from src.apps.analytics.dependencies import get_analytics

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Provide a disabled (no-op) analytics service for tests
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
    
    # Disable rate limiting for tests - handle both main limiter and route limiters
    if hasattr(app.state, 'limiter'):
        original_enabled = app.state.limiter.enabled
        app.state.limiter.enabled = False
    else:
        original_enabled = None
    
    # Also disable limiters in individual route modules
    limiters_to_restore = []
    try:
        from src.apps.iam.api.v1.auth import signup, login, password
        for module in [signup, login, password]:
            if hasattr(module, 'limiter'):
                limiters_to_restore.append((module.limiter, module.limiter.enabled))
                module.limiter.enabled = False
    except Exception:
        pass
    
    # Mock email service to avoid sending real emails
    with patch("src.apps.iam.services.email.EmailService.send_welcome_email", new_callable=AsyncMock):
        with patch("src.apps.iam.services.email.EmailService.send_verification_email", new_callable=AsyncMock):
            with patch("src.apps.iam.services.email.EmailService.send_password_reset_email", new_callable=AsyncMock):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as test_client:
                    yield test_client
    
    # Restore rate limiting after test
    if original_enabled is not None:
        app.state.limiter.enabled = original_enabled
    
    # Restore module limiters
    for limiter, was_enabled in limiters_to_restore:
        limiter.enabled = was_enabled
    
    CasbinEnforcer.reset()
    db_session_module.async_session_factory = original_async_session_factory
    app.dependency_overrides.clear()
