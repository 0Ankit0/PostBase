from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlmodel import select

from src.apps.core.config import settings
from src.apps.multitenancy.models.tenant import Tenant
from src.postbase.capabilities.functions.contracts import FunctionInvokeRequest
from src.postbase.domain.models import Environment, ExecutionRecord, FunctionDefinition, Project
from src.postbase.providers.functions.celery_runtime import CeleryRuntimeFunctionsProvider


async def _build_runtime_context(db_session):
    tenant = Tenant(name="Tenant", slug="tenant")
    db_session.add(tenant)
    await db_session.flush()

    project = Project(tenant_id=tenant.id, name="Project", slug="project")
    db_session.add(project)
    await db_session.flush()

    environment = Environment(project_id=project.id, name="Development", slug="dev")
    db_session.add(environment)
    await db_session.flush()

    function = FunctionDefinition(
        environment_id=environment.id,
        slug="echoer",
        name="Echoer",
        runtime_profile="celery-runtime",
        handler_type="echo",
    )
    db_session.add(function)
    await db_session.flush()
    await db_session.commit()

    context = SimpleNamespace(db=db_session, environment_id=environment.id, project_id=project.id)
    return context, function


@pytest.mark.asyncio
async def test_duplicate_submit_returns_cached_execution_within_replay_window(db_session):
    provider = CeleryRuntimeFunctionsProvider()
    context, function = await _build_runtime_context(db_session)

    request = FunctionInvokeRequest(payload={"message": "hello"}, invocation_type="sync")
    first = await provider.invoke(context, function.id, request, idempotency_key="dup-1")
    duplicate = await provider.invoke(context, function.id, request, idempotency_key="dup-1")

    assert duplicate.id == first.id
    rows = (
        await db_session.execute(
            select(ExecutionRecord).where(
                ExecutionRecord.environment_id == context.environment_id,
                ExecutionRecord.function_definition_id == function.id,
                ExecutionRecord.idempotency_key == "dup-1",
            )
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_delayed_duplicate_past_replay_window_creates_new_execution(db_session):
    provider = CeleryRuntimeFunctionsProvider()
    context, function = await _build_runtime_context(db_session)

    replay_window_seconds = settings.POSTBASE_IDEMPOTENCY_REPLAY_WINDOW_SECONDS
    request = FunctionInvokeRequest(payload={"message": "hello"}, invocation_type="sync")
    first = await provider.invoke(context, function.id, request, idempotency_key="dup-2")

    first_row = await db_session.get(ExecutionRecord, first.id)
    assert first_row is not None
    first_row.started_at = datetime.now(timezone.utc) - timedelta(seconds=replay_window_seconds + 1)
    await db_session.commit()

    duplicate = await provider.invoke(context, function.id, request, idempotency_key="dup-2")

    assert duplicate.id != first.id


@pytest.mark.asyncio
async def test_timeout_recovery_persists_correlation_and_retry_lineage(db_session):
    provider = CeleryRuntimeFunctionsProvider()
    context, function = await _build_runtime_context(db_session)

    execution = await provider.invoke(
        context,
        function.id,
        FunctionInvokeRequest(
            payload={"simulate_duration_ms": 250, "message": "recover"},
            invocation_type="sync",
            timeout_ms=50,
        ),
        idempotency_key="timeout-1",
        correlation_id="corr-timeout-1",
    )

    assert execution.status == "completed"
    assert execution.retry_count == 1
    assert execution.retry_of_execution_id is not None
    assert execution.correlation_id == "corr-timeout-1"

    parent = await db_session.get(ExecutionRecord, execution.retry_of_execution_id)
    assert parent is not None
    assert parent.status == "timed_out"
    assert parent.correlation_id == execution.correlation_id
