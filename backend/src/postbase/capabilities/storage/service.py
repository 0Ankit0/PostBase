from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import select

from src.postbase.capabilities.facade_base import CapabilityFacadeBase
from src.postbase.domain.enums import CapabilityKey
from src.postbase.domain.models import Environment


@dataclass
class StorageTaskContext:
    db: object
    project_id: int
    environment_id: int
    auth_user_id: int | None = None
    service_role: bool = True
    base_url: str = "http://localhost"


class StorageFacade(CapabilityFacadeBase):
    capability = CapabilityKey.STORAGE


async def run_storage_retention_for_environment(db, *, environment: Environment) -> dict[str, int]:
    facade = StorageFacade()
    context = StorageTaskContext(db=db, project_id=environment.project_id, environment_id=environment.id)
    provider = await facade.resolve_provider(context)
    result = await provider.run_retention(context, now=datetime.now(timezone.utc))
    return result.model_dump()


async def run_storage_retention_for_due_environments(db, *, limit: int = 200) -> dict[str, int]:
    environments = (await db.execute(select(Environment).where(Environment.is_active == True).limit(limit))).scalars().all()
    totals = {"scanned_files": 0, "deleted_files": 0, "updated_rules": 0, "environments": 0}
    for environment in environments:
        result = await run_storage_retention_for_environment(db, environment=environment)
        totals["scanned_files"] += result.get("scanned_files", 0)
        totals["deleted_files"] += result.get("deleted_files", 0)
        totals["updated_rules"] += result.get("updated_rules", 0)
        totals["environments"] += 1
    return totals
