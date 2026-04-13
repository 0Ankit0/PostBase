from __future__ import annotations

SDK_LIVE_FIXTURES = {
    "list_provider_catalog": {
        "method": "GET",
        "path": "/api/v1/provider-catalog",
        "expected_status": 200,
    },
    "list_projects": {
        "method": "GET",
        "path": "/api/v1/projects",
        "expected_status": 401,
    },
}
