from __future__ import annotations

import pytest

from .fixtures_sdk_contracts import SDK_LIVE_FIXTURES


@pytest.mark.asyncio
async def test_live_api_fixtures_match_expected_status_codes(client):
    for fixture in SDK_LIVE_FIXTURES.values():
        response = await client.request(fixture["method"], fixture["path"])
        assert response.status_code == fixture["expected_status"], response.text


@pytest.mark.asyncio
async def test_openapi_contains_sdk_fixture_routes(client):
    openapi_response = await client.get("/openapi.json")
    assert openapi_response.status_code == 200
    spec = openapi_response.json()
    paths = spec.get("paths", {})
    for fixture in SDK_LIVE_FIXTURES.values():
        assert fixture["path"] in paths
