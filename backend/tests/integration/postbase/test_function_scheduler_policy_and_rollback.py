from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import select

from src.apps.multitenancy.models.tenant import Tenant
from src.postbase.capabilities.functions.contracts import FunctionCreateRequest, FunctionInvokeRequest, FunctionScheduleCreateRequest
from src.postbase.domain.models import (
    Environment,
    FunctionDefinition,
    FunctionDeploymentEvent,
    FunctionDeploymentRevision,
    FunctionSchedule,
    Project,
)
from src.postbase.providers.functions.celery_runtime import CeleryRuntimeFunctionsProvider


async def _seed_context(db_session):
    tenant = Tenant(name="Tenant", slug="tenant")
    db_session.add(tenant)
    await db_session.flush()
    project = Project(
        tenant_id=tenant.id,
        name="Project",
        slug="project",
        env_policy_json={"allow": ["PUBLIC"], "deny": ["PROJECT_DENIED"]},
    )
    db_session.add(project)
    await db_session.flush()
    environment = Environment(
        project_id=project.id,
        name="Dev",
        slug="dev",
        env_policy_json={"deny": ["ENV_DENIED"]},
    )
    db_session.add(environment)
    await db_session.flush()
    await db_session.commit()
    return SimpleNamespace(
        db=db_session,
        environment_id=environment.id,
        project_id=project.id,
        actor_user_id=None,
        project_env_policy_allow=["PUBLIC"],
        project_env_policy_deny=["PROJECT_DENIED"],
        environment_env_policy_allow=[],
        environment_env_policy_deny=["ENV_DENIED"],
    )


@pytest.mark.asyncio
async def test_schedule_misfire_is_rejected_when_grace_window_exceeded(db_session):
    provider = CeleryRuntimeFunctionsProvider()
    context = await _seed_context(db_session)

    function = await provider.create_function(
        context,
        FunctionCreateRequest(slug="jobber", name="Jobber", handler_type="echo", runtime_profile="celery-runtime"),
    )
    schedule = await provider.create_schedule(
        context,
        function.id,
        FunctionScheduleCreateRequest(name="nightly", schedule_type="interval", interval_seconds=60, misfire_grace_seconds=1),
    )
    schedule_row = await db_session.get(FunctionSchedule, schedule.id)
    assert schedule_row is not None
    schedule_row.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await provider.run_schedule_now(context, function.id, schedule.id)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_environment_variable_policy_inheritance_and_override_is_enforced(db_session):
    provider = CeleryRuntimeFunctionsProvider()
    context = await _seed_context(db_session)

    function = await provider.create_function(
        context,
        FunctionCreateRequest(
            slug="policy-job",
            name="Policy Job",
            handler_type="echo",
            runtime_profile="celery-runtime",
            env_policy_json={"allow": ["PUBLIC", "FUNCTION_ONLY"], "deny": ["FUNC_DENIED"]},
        ),
    )

    with pytest.raises(HTTPException):
        await provider.invoke(
            context,
            function.id,
            FunctionInvokeRequest(payload={"env": {"ENV_DENIED": "x"}}, invocation_type="sync"),
        )

    success = await provider.invoke(
        context,
        function.id,
        FunctionInvokeRequest(payload={"env": {"FUNCTION_ONLY": "ok"}}, invocation_type="sync"),
    )
    assert success.status == "completed"


@pytest.mark.asyncio
async def test_can_rollback_function_to_prior_revision(db_session):
    provider = CeleryRuntimeFunctionsProvider()
    context = await _seed_context(db_session)

    created = await provider.create_function(
        context,
        FunctionCreateRequest(slug="rollback-job", name="Rollback Job", handler_type="echo", runtime_profile="celery-runtime"),
    )

    function_row = await db_session.get(FunctionDefinition, created.id)
    assert function_row is not None
    function_row.handler_type = "template"
    function_row.config_json = {"template": "new"}
    db_session.add(
        FunctionDeploymentRevision(
            function_definition_id=function_row.id,
            environment_id=context.environment_id,
            revision=2,
            source_ref="r2",
            handler_type="template",
            runtime_profile=function_row.runtime_profile,
            config_json=function_row.config_json,
            env_policy_json=function_row.env_policy_json,
        )
    )
    await db_session.commit()

    revisions = (
        await db_session.execute(
            select(FunctionDeploymentRevision).where(
                FunctionDeploymentRevision.function_definition_id == function_row.id,
                FunctionDeploymentRevision.revision == 1,
            )
        )
    ).scalars().first()
    assert revisions is not None

    rolled_back = await provider.rollback_revision(context, function_row.id, revisions.id)
    assert rolled_back.handler_type == "echo"

    rollback_event = (
        await db_session.execute(
            select(FunctionDeploymentEvent).where(
                FunctionDeploymentEvent.function_definition_id == function_row.id,
                FunctionDeploymentEvent.event_type == "rollback",
            )
        )
    ).scalars().first()
    assert rollback_event is not None
