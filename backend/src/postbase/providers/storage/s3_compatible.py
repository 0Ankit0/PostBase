from __future__ import annotations

from src.apps.core.config import settings
from src.postbase.platform.contracts import ProviderHealth
from src.postbase.providers.storage.base import StorageProviderBase


class S3CompatibleStorageProvider(StorageProviderBase):
    provider_key = "s3-compatible"

    async def health(self) -> ProviderHealth:
        endpoint = settings.S3_ENDPOINT_URL or settings.MEDIA_BASE_URL or "local-media"
        return ProviderHealth(ready=True, detail=f"endpoint={endpoint}")
