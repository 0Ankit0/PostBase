from __future__ import annotations

from src.postbase.capabilities.facade_base import CapabilityFacadeBase
from src.postbase.capabilities.functions.contracts import (
    ExecutionRead,
    FunctionDeploymentEventRead,
    FunctionDeploymentRevisionRead,
    FunctionScheduleCreateRequest,
    FunctionScheduleRead,
)
from src.postbase.domain.enums import CapabilityKey


class FunctionsFacade(CapabilityFacadeBase):
    capability = CapabilityKey.FUNCTIONS

    async def create_schedule(self, context, function_id: int, payload: FunctionScheduleCreateRequest) -> FunctionScheduleRead:
        provider = await self.resolve_provider(context)
        return await provider.create_schedule(context, function_id, payload)

    async def pause_schedule(self, context, function_id: int, schedule_id: int) -> FunctionScheduleRead:
        provider = await self.resolve_provider(context)
        return await provider.pause_schedule(context, function_id, schedule_id)

    async def resume_schedule(self, context, function_id: int, schedule_id: int) -> FunctionScheduleRead:
        provider = await self.resolve_provider(context)
        return await provider.resume_schedule(context, function_id, schedule_id)

    async def run_schedule_now(self, context, function_id: int, schedule_id: int) -> ExecutionRead:
        provider = await self.resolve_provider(context)
        return await provider.run_schedule_now(context, function_id, schedule_id)

    async def delete_schedule(self, context, function_id: int, schedule_id: int) -> None:
        provider = await self.resolve_provider(context)
        await provider.delete_schedule(context, function_id, schedule_id)

    async def list_deployment_history(
        self, context, function_id: int, *, skip: int, limit: int
    ) -> list[FunctionDeploymentEventRead]:
        provider = await self.resolve_provider(context)
        result = await provider.list_deployment_history(context, function_id, skip=skip, limit=limit)
        return result.items

    async def list_revisions(self, context, function_id: int, *, skip: int, limit: int) -> list[FunctionDeploymentRevisionRead]:
        provider = await self.resolve_provider(context)
        result = await provider.list_revisions(context, function_id, skip=skip, limit=limit)
        return result.items
