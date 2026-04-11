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
    FunctionInvokeRequest,
    FunctionRead,
)
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import ExecutionRecord, FunctionDefinition
from src.postbase.platform.access import validate_identifier
from src.postbase.platform.contracts import CapabilityProfile, ProviderHealth
from src.postbase.platform.usage import record_usage


class InlineRuntimeFunctionsProvider:
    def profile(self) -> CapabilityProfile:
        return CapabilityProfile(
            capability=CapabilityKey.FUNCTIONS,
            provider_key="inline-runtime",
            supported_operations=["create", "list", "invoke", "executions"],
            optional_features=["sync"],
            limits={"max_payload_bytes": 65536},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(ready=True, detail="inline execution enabled")

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
            runtime_profile=self.profile().provider_key,
            config_json=payload.config_json,
        )
        db.add(row)
        await db.flush()
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
    ) -> ExecutionRead:
        if payload.invocation_type != "sync":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="inline-runtime only supports sync invocation",
            )
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        function = await db.get(FunctionDefinition, function_id)
        if function is None or function.environment_id != context.environment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Function not found")
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
                status="canceled",
                input_json=payload.payload,
                output_json={},
                log_excerpt="inline invocation canceled before execution",
                completed_at=now,
            )
            db.add(canceled)
            await db.flush()
            await db.commit()
            return self._execution_read(canceled)
        if function.handler_type == "echo":
            output = {"echo": payload.payload, "provider": "inline-runtime"}
        elif function.handler_type == "template":
            output = {"message": function.config_json.get("template", "ok"), "provider": "inline-runtime"}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported handler type")
        if payload.timeout_ms is not None:
            simulated_duration = int(payload.payload.get("simulate_duration_ms", 0))
            if simulated_duration > payload.timeout_ms:
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
                    status="timed_out",
                    input_json=payload.payload,
                    output_json={},
                    error_text="inline adapter timeout exceeded",
                    log_excerpt="inline adapter timeout",
                    completed_at=now,
                )
                db.add(timeout_execution)
                await db.flush()
                recovery_retries = min(settings.POSTBASE_FUNCTION_TIMEOUT_RECOVERY_RETRIES, 1)
                if recovery_retries > 0:
                    recovered_output = {**output, "timeout_recovered": True}
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
                        status="completed",
                        input_json=payload.payload,
                        output_json=recovered_output,
                        log_excerpt="inline adapter timeout recovery succeeded",
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
            status="completed",
            input_json=payload.payload,
            output_json=output,
            log_excerpt="inline invocation completed",
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

    def _function_read(self, row: FunctionDefinition) -> FunctionRead:
        return FunctionRead(
            id=row.id,
            slug=row.slug,
            name=row.name,
            handler_type=row.handler_type,
            runtime_profile=row.runtime_profile,
            config_json=row.config_json,
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
            status=row.status,
            input_json=row.input_json,
            output_json=row.output_json,
            error_text=row.error_text,
            started_at=row.started_at,
            completed_at=row.completed_at,
            log_excerpt=row.log_excerpt,
        )
