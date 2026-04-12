from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from src.apps.core.config import settings
from src.apps.core.schemas import PaginatedResponse
from src.postbase.capabilities.functions.contracts import (
    ExecutionRead,
    FunctionCreateRequest,
    FunctionDeploymentEventRead,
    FunctionDeploymentRevisionRead,
    FunctionInvokeRequest,
    FunctionRead,
    FunctionScheduleCreateRequest,
    FunctionScheduleRead,
)
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import (
    ExecutionRecord,
    FunctionDefinition,
    FunctionDeploymentEvent,
    FunctionDeploymentRevision,
    FunctionSchedule,
)
from src.postbase.platform.access import validate_identifier
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


class CeleryRuntimeFunctionsProvider:
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.FUNCTIONS,
            provider_key="celery-runtime",
            supported_operations=[
                "create",
                "list",
                "invoke",
                "executions",
                "schedules",
                "deployment_history",
                "revisions",
            ],
            optional_features=["sync", "async"],
            limits={"max_payload_bytes": 1048576},
        )

    async def health(self) -> ProviderHealth:
        detail = (
            "task_always_eager=true"
            if settings.CELERY_TASK_ALWAYS_EAGER
            else f"broker={settings.CELERY_BROKER_URL}"
        )
        return ProviderHealth(ready=True, detail=detail)

    async def create_function(self, context, payload: FunctionCreateRequest) -> FunctionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        slug = validate_identifier(payload.slug, "Function slug")
        existing = (
            await db.execute(
                select(FunctionDefinition).where(
                    FunctionDefinition.environment_id == context.environment_id,
                    FunctionDefinition.slug == slug,
                )
            )
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Function slug already exists")
        row = FunctionDefinition(
            environment_id=context.environment_id,
            slug=slug,
            name=payload.name,
            handler_type=payload.handler_type,
            runtime_profile=payload.runtime_profile,
            config_json=payload.config_json,
            env_policy_json=payload.env_policy_json,
        )
        db.add(row)
        await db.flush()
        db.add(
            FunctionDeploymentRevision(
                function_definition_id=row.id,
                environment_id=context.environment_id,
                revision=1,
                source_ref=row.code_ref,
                handler_type=row.handler_type,
                runtime_profile=row.runtime_profile,
                config_json=row.config_json,
                env_policy_json=row.env_policy_json,
                deployed_by_user_id=getattr(context, "actor_user_id", None),
            )
        )
        db.add(
            FunctionDeploymentEvent(
                function_definition_id=row.id,
                environment_id=context.environment_id,
                event_type="deploy",
                actor_user_id=getattr(context, "actor_user_id", None),
                metadata_json={"reason": "initial_create"},
            )
        )
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.FUNCTIONS.value,
            metric_key="create_function",
        )
        await db.commit()
        return self._function_read(row)

    async def list_functions(self, context, *, skip: int, limit: int) -> PaginatedResponse[FunctionRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        total = (
            await db.execute(
                select(func.count()).select_from(FunctionDefinition).where(FunctionDefinition.environment_id == context.environment_id)
            )
        ).scalar_one()
        rows = (
            await db.execute(
                select(FunctionDefinition)
                .where(FunctionDefinition.environment_id == context.environment_id)
                .order_by(FunctionDefinition.id.desc())
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.FUNCTIONS.value,
            metric_key="list_functions",
        )
        return PaginatedResponse[FunctionRead].create(
            items=[self._function_read(item) for item in rows],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def invoke(
        self,
        context,
        function_id: int,
        payload: FunctionInvokeRequest,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        retry_of_execution_id: int | None = None,
        schedule_id: int | None = None,
        trigger_source: str = "manual",
        execution_metadata: dict | None = None,
    ) -> ExecutionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        function = await db.get(FunctionDefinition, function_id)
        if function is None or function.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Function not found")
        self._enforce_env_policy(context, function, payload.payload)
        now = datetime.now(timezone.utc)
        replay_window_start = now - timedelta(seconds=settings.POSTBASE_IDEMPOTENCY_REPLAY_WINDOW_SECONDS)
        resolved_correlation_id = correlation_id or str(uuid4())
        if idempotency_key:
            existing = (
                await db.execute(
                    select(ExecutionRecord).where(
                        ExecutionRecord.environment_id == context.environment_id,
                        ExecutionRecord.function_definition_id == function.id,
                        ExecutionRecord.idempotency_key == idempotency_key,
                        ExecutionRecord.started_at >= replay_window_start,
                    ).order_by(ExecutionRecord.started_at.desc())
                )
            ).scalars().first()
            if existing is not None:
                return self._execution_read(existing)
        if payload.cancel_requested:
            canceled = ExecutionRecord(
                function_definition_id=function.id,
                environment_id=context.environment_id,
                invocation_type=payload.invocation_type,
                idempotency_key=idempotency_key,
                correlation_id=resolved_correlation_id,
                retry_of_execution_id=retry_of_execution_id,
                retry_count=0,
                timeout_ms=payload.timeout_ms,
                cancel_requested=True,
                schedule_id=schedule_id,
                trigger_source=trigger_source,
                execution_metadata_json=execution_metadata or {},
                status="canceled",
                input_json=payload.payload,
                output_json={},
                log_excerpt="celery-runtime invocation canceled before execution",
                completed_at=now,
            )
            db.add(canceled)
            await db.flush()
            await db.commit()
            return self._execution_read(canceled)
        try:
            output = self._execute_handler(
                function,
                payload.payload,
                context,
                timeout_ms=payload.timeout_ms,
                cancel_requested=payload.cancel_requested,
            )
        except TimeoutError:
            timeout_execution = ExecutionRecord(
                function_definition_id=function.id,
                environment_id=context.environment_id,
                invocation_type=payload.invocation_type,
                idempotency_key=idempotency_key,
                correlation_id=resolved_correlation_id,
                retry_of_execution_id=retry_of_execution_id,
                retry_count=0,
                timeout_ms=payload.timeout_ms,
                cancel_requested=payload.cancel_requested,
                schedule_id=schedule_id,
                trigger_source=trigger_source,
                execution_metadata_json=execution_metadata or {},
                status="timed_out",
                input_json=payload.payload,
                output_json={},
                error_text="celery-runtime adapter timeout exceeded",
                log_excerpt="celery-runtime adapter timeout",
                completed_at=now,
            )
            db.add(timeout_execution)
            await db.flush()
            recovery_retries = min(settings.POSTBASE_FUNCTION_TIMEOUT_RECOVERY_RETRIES, 1)
            if recovery_retries > 0:
                output = self._execute_handler(
                    function,
                    payload.payload,
                    context,
                    timeout_ms=None,
                    cancel_requested=payload.cancel_requested,
                )
                recovered_execution = ExecutionRecord(
                    function_definition_id=function.id,
                    environment_id=context.environment_id,
                    invocation_type=payload.invocation_type,
                    idempotency_key=idempotency_key,
                    correlation_id=resolved_correlation_id,
                    replay_of_execution_id=timeout_execution.id,
                    retry_of_execution_id=timeout_execution.id,
                    retry_count=timeout_execution.retry_count + 1,
                    timeout_ms=payload.timeout_ms,
                    cancel_requested=payload.cancel_requested,
                    schedule_id=schedule_id,
                    trigger_source=trigger_source,
                    execution_metadata_json=execution_metadata or {},
                    status="completed",
                    input_json=payload.payload,
                    output_json={**output, "timeout_recovered": True},
                    log_excerpt="celery-runtime timeout recovery succeeded",
                    completed_at=now,
                )
                db.add(recovered_execution)
                await db.flush()
                await db.commit()
                return self._execution_read(recovered_execution)
            await db.commit()
            return self._execution_read(timeout_execution)
        execution = ExecutionRecord(
            function_definition_id=function.id,
            environment_id=context.environment_id,
            invocation_type=payload.invocation_type,
            idempotency_key=idempotency_key,
            correlation_id=resolved_correlation_id,
            retry_of_execution_id=retry_of_execution_id,
            retry_count=0,
            timeout_ms=payload.timeout_ms,
            cancel_requested=payload.cancel_requested,
            schedule_id=schedule_id,
            trigger_source=trigger_source,
            execution_metadata_json=execution_metadata or {},
            status="completed",
            input_json=payload.payload,
            output_json=output,
            log_excerpt="celery-runtime invocation completed",
            completed_at=now,
        )
        db.add(execution)
        await db.flush()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.FUNCTIONS.value,
            metric_key="invoke_function",
        )
        await db.commit()
        return self._execution_read(execution)

    async def list_executions(self, context, function_id: int, *, skip: int, limit: int) -> PaginatedResponse[ExecutionRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        total = (
            await db.execute(
                select(func.count())
                .select_from(ExecutionRecord)
                .where(
                    ExecutionRecord.environment_id == context.environment_id,
                    ExecutionRecord.function_definition_id == function_id,
                )
            )
        ).scalar_one()
        rows = (
            await db.execute(
                select(ExecutionRecord).where(
                    ExecutionRecord.environment_id == context.environment_id,
                    ExecutionRecord.function_definition_id == function_id,
                )
                .order_by(ExecutionRecord.id.desc())
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.FUNCTIONS.value,
            metric_key="list_executions",
        )
        return PaginatedResponse[ExecutionRead].create(
            items=[self._execution_read(item) for item in rows],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def create_schedule(self, context, function_id: int, payload: FunctionScheduleCreateRequest) -> FunctionScheduleRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        function = await db.get(FunctionDefinition, function_id)
        if function is None or function.environment_id != context.environment_id:
            raise HTTPException(status_code=404, detail="Function not found")
        schedule = FunctionSchedule(
            function_definition_id=function.id,
            environment_id=context.environment_id,
            name=payload.name,
            schedule_type=payload.schedule_type,
            cron_expr=payload.cron_expr,
            interval_seconds=payload.interval_seconds,
            timezone=payload.timezone,
            status="active",
            misfire_grace_seconds=payload.misfire_grace_seconds,
            max_jitter_seconds=payload.max_jitter_seconds,
        )
        db.add(schedule)
        await db.flush()
        await db.commit()
        return self._schedule_read(schedule)

    async def list_schedules(self, context, function_id: int, *, skip: int, limit: int) -> PaginatedResponse[FunctionScheduleRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        total = (
            await db.execute(
                select(func.count()).select_from(FunctionSchedule).where(
                    FunctionSchedule.environment_id == context.environment_id,
                    FunctionSchedule.function_definition_id == function_id,
                    FunctionSchedule.status != "deleted",
                )
            )
        ).scalar_one()
        rows = (
            await db.execute(
                select(FunctionSchedule).where(
                    FunctionSchedule.environment_id == context.environment_id,
                    FunctionSchedule.function_definition_id == function_id,
                    FunctionSchedule.status != "deleted",
                ).order_by(FunctionSchedule.id.desc()).offset(skip).limit(limit)
            )
        ).scalars().all()
        return PaginatedResponse[FunctionScheduleRead].create(
            items=[self._schedule_read(row) for row in rows], total=total, skip=skip, limit=limit
        )

    async def pause_schedule(self, context, function_id: int, schedule_id: int) -> FunctionScheduleRead:
        schedule = await self._get_schedule(context, function_id, schedule_id)
        schedule.status = "paused"
        schedule.updated_at = datetime.now(timezone.utc)
        await context.db.commit()
        return self._schedule_read(schedule)

    async def resume_schedule(self, context, function_id: int, schedule_id: int) -> FunctionScheduleRead:
        schedule = await self._get_schedule(context, function_id, schedule_id)
        schedule.status = "active"
        schedule.updated_at = datetime.now(timezone.utc)
        await context.db.commit()
        return self._schedule_read(schedule)

    async def run_schedule_now(self, context, function_id: int, schedule_id: int) -> ExecutionRead:
        schedule = await self._get_schedule(context, function_id, schedule_id)
        now = datetime.now(timezone.utc)
        misfired = bool(
            schedule.next_run_at and schedule.misfire_grace_seconds >= 0
            and (now - schedule.next_run_at).total_seconds() > schedule.misfire_grace_seconds
        )
        if misfired:
            raise HTTPException(status_code=409, detail="Schedule misfire exceeded grace window")
        execution = await self.invoke(
            context,
            function_id,
            FunctionInvokeRequest(payload={"schedule_name": schedule.name}, invocation_type="sync"),
            schedule_id=schedule.id,
            trigger_source="schedule",
            execution_metadata={"schedule_status": schedule.status},
        )
        schedule.last_scheduled_at = now
        schedule.last_run_at = now
        schedule.last_execution_id = execution.id
        schedule.run_count += 1
        schedule.updated_at = now
        await context.db.commit()
        return execution

    async def delete_schedule(self, context, function_id: int, schedule_id: int) -> None:
        schedule = await self._get_schedule(context, function_id, schedule_id)
        schedule.status = "deleted"
        schedule.updated_at = datetime.now(timezone.utc)
        await context.db.commit()

    async def list_deployment_history(self, context, function_id: int, *, skip: int, limit: int) -> PaginatedResponse[FunctionDeploymentEventRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        total = (
            await db.execute(select(func.count()).select_from(FunctionDeploymentEvent).where(
                FunctionDeploymentEvent.environment_id == context.environment_id,
                FunctionDeploymentEvent.function_definition_id == function_id,
            ))
        ).scalar_one()
        rows = (
            await db.execute(select(FunctionDeploymentEvent).where(
                FunctionDeploymentEvent.environment_id == context.environment_id,
                FunctionDeploymentEvent.function_definition_id == function_id,
            ).order_by(FunctionDeploymentEvent.id.desc()).offset(skip).limit(limit))
        ).scalars().all()
        return PaginatedResponse[FunctionDeploymentEventRead].create(
            items=[self._deployment_event_read(row) for row in rows], total=total, skip=skip, limit=limit
        )

    async def list_revisions(self, context, function_id: int, *, skip: int, limit: int) -> PaginatedResponse[FunctionDeploymentRevisionRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        total = (
            await db.execute(select(func.count()).select_from(FunctionDeploymentRevision).where(
                FunctionDeploymentRevision.environment_id == context.environment_id,
                FunctionDeploymentRevision.function_definition_id == function_id,
            ))
        ).scalar_one()
        rows = (
            await db.execute(select(FunctionDeploymentRevision).where(
                FunctionDeploymentRevision.environment_id == context.environment_id,
                FunctionDeploymentRevision.function_definition_id == function_id,
            ).order_by(FunctionDeploymentRevision.revision.desc()).offset(skip).limit(limit))
        ).scalars().all()
        return PaginatedResponse[FunctionDeploymentRevisionRead].create(
            items=[self._deployment_revision_read(row) for row in rows], total=total, skip=skip, limit=limit
        )

    async def rollback_revision(self, context, function_id: int, revision_id: int) -> FunctionRead:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        function = await db.get(FunctionDefinition, function_id)
        revision = await db.get(FunctionDeploymentRevision, revision_id)
        if function is None or revision is None or function.environment_id != context.environment_id or revision.function_definition_id != function_id:
            raise HTTPException(status_code=404, detail="Revision not found")
        function.handler_type = revision.handler_type
        function.runtime_profile = revision.runtime_profile
        function.config_json = revision.config_json
        function.env_policy_json = revision.env_policy_json
        function.updated_at = datetime.now(timezone.utc)
        db.add(
            FunctionDeploymentEvent(
                function_definition_id=function_id,
                environment_id=context.environment_id,
                revision_id=revision.id,
                event_type="rollback",
                actor_user_id=getattr(context, "actor_user_id", None),
                metadata_json={"rollback_to_revision": revision.revision},
            )
        )
        await db.commit()
        return self._function_read(function)

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
        if timeout_ms is not None:
            simulated_duration = int(payload.get("simulate_duration_ms", 0))
            if simulated_duration > timeout_ms:
                raise TimeoutError("runtime adapter timeout exceeded")
        if function.handler_type == "echo":
            return {
                "echo": payload,
                "function_slug": function.slug,
                "environment_id": context.environment_id,
                "project_id": context.project_id,
                "timeout_ms": timeout_ms,
                "cancel_requested": cancel_requested,
            }
        if function.handler_type == "template":
            template = function.config_json.get("template", "ok")
            return {"message": template, "payload": payload}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported handler type")

    def _function_read(self, row: FunctionDefinition) -> FunctionRead:
        return FunctionRead(
            id=row.id,
            slug=row.slug,
            name=row.name,
            handler_type=row.handler_type,
            runtime_profile=row.runtime_profile,
            config_json=row.config_json,
            env_policy_json=row.env_policy_json,
            is_active=row.is_active,
        )

    def _execution_read(self, row: ExecutionRecord) -> ExecutionRead:
        return ExecutionRead(
            id=row.id,
            function_definition_id=row.function_definition_id,
            invocation_type=row.invocation_type,
            idempotency_key=row.idempotency_key,
            correlation_id=row.correlation_id,
            replay_of_execution_id=row.replay_of_execution_id,
            retry_of_execution_id=row.retry_of_execution_id,
            retry_count=row.retry_count,
            timeout_ms=row.timeout_ms,
            cancel_requested=row.cancel_requested,
            schedule_id=row.schedule_id,
            trigger_source=row.trigger_source,
            execution_metadata_json=row.execution_metadata_json,
            status=row.status,
            input_json=row.input_json,
            output_json=row.output_json,
            error_text=row.error_text,
            started_at=row.started_at,
            completed_at=row.completed_at,
            log_excerpt=row.log_excerpt,
        )

    async def _get_schedule(self, context, function_id: int, schedule_id: int) -> FunctionSchedule:
        schedule = await context.db.get(FunctionSchedule, schedule_id)
        if (
            schedule is None
            or schedule.environment_id != context.environment_id
            or schedule.function_definition_id != function_id
            or schedule.status == "deleted"
        ):
            raise HTTPException(status_code=404, detail="Schedule not found")
        return schedule

    def _schedule_read(self, row: FunctionSchedule) -> FunctionScheduleRead:
        return FunctionScheduleRead(
            id=row.id,
            function_definition_id=row.function_definition_id,
            name=row.name,
            schedule_type=row.schedule_type,
            cron_expr=row.cron_expr,
            interval_seconds=row.interval_seconds,
            timezone=row.timezone,
            status=row.status,
            misfire_grace_seconds=row.misfire_grace_seconds,
            max_jitter_seconds=row.max_jitter_seconds,
            last_scheduled_at=row.last_scheduled_at,
            last_run_at=row.last_run_at,
            next_run_at=row.next_run_at,
            run_count=row.run_count,
            last_execution_id=row.last_execution_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _deployment_revision_read(self, row: FunctionDeploymentRevision) -> FunctionDeploymentRevisionRead:
        return FunctionDeploymentRevisionRead(
            id=row.id,
            function_definition_id=row.function_definition_id,
            revision=row.revision,
            source_ref=row.source_ref,
            handler_type=row.handler_type,
            runtime_profile=row.runtime_profile,
            config_json=row.config_json,
            env_policy_json=row.env_policy_json,
            deployed_by_user_id=row.deployed_by_user_id,
            created_at=row.created_at,
        )

    def _deployment_event_read(self, row: FunctionDeploymentEvent) -> FunctionDeploymentEventRead:
        return FunctionDeploymentEventRead(
            id=row.id,
            function_definition_id=row.function_definition_id,
            revision_id=row.revision_id,
            event_type=row.event_type,
            actor_user_id=row.actor_user_id,
            metadata_json=row.metadata_json,
            created_at=row.created_at,
        )

    def _enforce_env_policy(self, context, function: FunctionDefinition, payload: dict) -> None:
        if not payload:
            return
        requested_env = payload.get("env", {})
        if not isinstance(requested_env, dict):
            return
        denied_keys = set(function.env_policy_json.get("deny", []))
        allowed_keys = set(function.env_policy_json.get("allow", []))
        # inheritance: project defaults -> environment overrides -> function overrides
        # project/environment scopes are opportunistically read from context attributes if present.
        denied_keys |= set(getattr(context, "project_env_policy_deny", []))
        denied_keys |= set(getattr(context, "environment_env_policy_deny", []))
        allowed_keys |= set(getattr(context, "project_env_policy_allow", []))
        allowed_keys |= set(getattr(context, "environment_env_policy_allow", []))
        for key in requested_env.keys():
            if key in denied_keys:
                raise HTTPException(status_code=403, detail=f"Environment variable '{key}' is denied by policy")
            if allowed_keys and key not in allowed_keys:
                raise HTTPException(status_code=403, detail=f"Environment variable '{key}' is outside allowed policy scope")
