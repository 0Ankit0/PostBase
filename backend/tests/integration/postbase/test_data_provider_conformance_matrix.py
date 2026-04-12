from __future__ import annotations

import pytest

from src.postbase.capabilities.data.contracts import DataMutationPayload, DataPagination, DataQueryRequest
from src.postbase.domain.enums import EnvironmentStage
from src.postbase.domain.models import DataNamespace, Environment, Project, TableDefinition
from src.apps.multitenancy.models.tenant import Tenant
from src.postbase.providers.data.postgres_compat import PostgresCompatDataProvider
from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider

from .fixtures_data_conformance import DATA_CONFORMANCE_ROWS, DATA_CONFORMANCE_SCENARIOS


class _ProviderContext:
    def __init__(self, db, environment_id: int) -> None:
        self.db = db
        self.environment_id = environment_id
        self.auth_user_id = None

    @property
    def service_role(self) -> bool:
        return True

    @property
    def authenticated(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_data_provider_conformance_matrix_for_canonical_filters_and_pagination(db_session):
    providers = {
        "postgres-native": PostgresNativeDataProvider(),
        "postgres-compat": PostgresCompatDataProvider(),
    }

    tenant = Tenant(name="Conformance Tenant", slug="conformance-tenant", description="")
    db_session.add(tenant)
    await db_session.flush()

    project = Project(tenant_id=tenant.id, name="Conformance", slug="conformance", description="")
    db_session.add(project)
    await db_session.flush()
    environment = Environment(project_id=project.id, name="Dev", slug="dev", stage=EnvironmentStage.DEVELOPMENT)
    db_session.add(environment)
    await db_session.flush()

    namespace = DataNamespace(environment_id=environment.id, name="app", physical_schema="app", status="active")
    db_session.add(namespace)
    await db_session.flush()
    table = TableDefinition(
        namespace_id=namespace.id,
        table_name="records",
        columns_json=[
            {"name": "title", "type": "string", "nullable": False},
            {"name": "category", "type": "string", "nullable": False},
            {"name": "score", "type": "integer", "nullable": True},
            {"name": "note", "type": "text", "nullable": True},
        ],
    )
    db_session.add(table)
    await db_session.commit()

    primary_provider = providers["postgres-native"]
    await primary_provider.create_table(db_session, namespace, table)
    for row in DATA_CONFORMANCE_ROWS:
        await primary_provider.create_row(
            _ProviderContext(db_session, environment.id),
            namespace="app",
            table="records",
            payload=DataMutationPayload(values=row),
        )

    baseline_by_scenario: dict[str, list[dict[str, object]]] = {}
    provider_results: dict[str, dict[str, list[dict[str, object]]]] = {}

    for provider_key, provider in providers.items():
        context = _ProviderContext(db_session, environment.id)
        scenario_results: dict[str, list[dict[str, object]]] = {}
        for scenario in DATA_CONFORMANCE_SCENARIOS:
            result = await provider.query_rows(
                context,
                DataQueryRequest(
                    namespace="app",
                    table="records",
                    filters=scenario["filters"],
                    sort=scenario["sort"],
                    pagination=DataPagination(limit=50, offset=0),
                ),
            )
            scenario_results[scenario["name"]] = result.rows
        provider_results[provider_key] = scenario_results

        paged = await provider.list_rows(context, "app", "records", skip=1, limit=2)
        scenario_results["pagination_window"] = list(paged.items)

        if not baseline_by_scenario:
            baseline_by_scenario = dict(scenario_results)

    for provider_key, scenario_results in provider_results.items():
        for scenario_name, expected_rows in baseline_by_scenario.items():
            actual_rows = scenario_results[scenario_name]
            assert [row.get("id") for row in actual_rows] == [row.get("id") for row in expected_rows], (
                f"{provider_key} diverged for {scenario_name}"
            )
