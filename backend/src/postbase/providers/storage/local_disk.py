from __future__ import annotations

from pathlib import Path

from src.apps.core.config import settings
from src.postbase.platform.contracts import ProviderHealth
from src.postbase.providers.storage.base import StorageProviderBase


class LocalDiskStorageProvider(StorageProviderBase):
    provider_key = "local-disk"

    async def health(self) -> ProviderHealth:
        media_path = Path(settings.MEDIA_DIR)
        ready = media_path.exists() or media_path.parent.exists()
        return ProviderHealth(ready=ready, detail=f"media_dir={media_path}")
