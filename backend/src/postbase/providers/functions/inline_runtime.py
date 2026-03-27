from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

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

    async def list_functions(self, context) -> list[FunctionRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        rows = (
            await db.execute(select(FunctionDefinition).where(FunctionDefinition.environment_id == context.environment_id))
        ).scalars().all()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.FUNCTIONS.value,
            metric_key="list_functions",
        )
        return [self._function_read(item) for item in rows]

    async def invoke(
        self,
        context,
        function_id: int,
        payload: FunctionInvokeRequest,
        idempotency_key: str | None = None,
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
        if idempotency_key:
            existing = (
                await db.execute(
                    select(ExecutionRecord).where(
                        ExecutionRecord.environment_id == context.environment_id,
                        ExecutionRecord.function_definition_id == function.id,
                        ExecutionRecord.idempotency_key == idempotency_key,
                    )
                )
            ).scalars().first()
            if existing is not None:
                replay = ExecutionRecord(
                    function_definition_id=function.id,
                    environment_id=context.environment_id,
                    invocation_type=payload.invocation_type,
                    idempotency_key=idempotency_key,
                    replay_of_execution_id=existing.id,
                    retry_count=existing.retry_count,
                    status=existing.status,
                    input_json=payload.payload,
                    output_json=existing.output_json,
                    error_text=existing.error_text,
                    log_excerpt="idempotency replay",
                    completed_at=datetime.now(timezone.utc),
                )
                db.add(replay)
                await db.flush()
                await db.commit()
                return self._execution_read(replay)
        if function.handler_type == "echo":
            output = {"echo": payload.payload, "provider": "inline-runtime"}
        elif function.handler_type == "template":
            output = {"message": function.config_json.get("template", "ok"), "provider": "inline-runtime"}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported handler type")
        execution = ExecutionRecord(
            function_definition_id=function.id,
            environment_id=context.environment_id,
            invocation_type=payload.invocation_type,
            idempotency_key=idempotency_key,
            retry_count=0,
            status="completed",
            input_json=payload.payload,
            output_json=output,
            log_excerpt="inline invocation completed",
            completed_at=datetime.now(timezone.utc),
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

    async def list_executions(self, context, function_id: int) -> list[ExecutionRead]:
        db: AsyncSession = context.db  # type: ignore[attr-defined]
        rows = (
            await db.execute(
                select(ExecutionRecord).where(
                    ExecutionRecord.environment_id == context.environment_id,
                    ExecutionRecord.function_definition_id == function_id,
                )
            )
        ).scalars().all()
        await record_usage(
            db,
            environment_id=context.environment_id,
            capability_key=CapabilityKey.FUNCTIONS.value,
            metric_key="list_executions",
        )
        return [self._execution_read(item) for item in rows]

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
            replay_of_execution_id=row.replay_of_execution_id,
            retry_count=row.retry_count,
            status=row.status,
            input_json=row.input_json,
            output_json=row.output_json,
            error_text=row.error_text,
            started_at=row.started_at,
            completed_at=row.completed_at,
            log_excerpt=row.log_excerpt,
        )
