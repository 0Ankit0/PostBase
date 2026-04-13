"""Auto-generated from backend/openapi/openapi.json."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class PostBaseSdkClient:
    def __init__(self, base_url: str, *, headers: Mapping[str, str] | None = None) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, headers=dict(headers or {}))

    async def close(self) -> None:
        await self._client.aclose()

    async def list_projects_api_v1_projects_get(self, *, params: Mapping[str, Any] | None = None) -> Any:
        response = await self._client.get('/api/v1/projects', params=params)
        response.raise_for_status()
        return response.json()

    async def list_provider_catalog_api_v1_provider_catalog_get(self, *, params: Mapping[str, Any] | None = None) -> Any:
        response = await self._client.get('/api/v1/provider-catalog', params=params)
        response.raise_for_status()
        return response.json()
