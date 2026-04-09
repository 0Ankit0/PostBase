import base64

import pytest
from sqlalchemy import text
from sqlmodel import select

from src.apps.iam.models.user import User
from src.apps.multitenancy.models.tenant import Tenant, TenantMember, TenantRole
from src.apps.iam.utils.hashid import encode_id
from src.postbase.domain.enums import BindingStatus, MigrationStatus
from src.postbase.domain.models import CapabilityBinding, DataNamespace, SchemaMigration, SchemaMigrationExecution, TableDefinition


@pytest.mark.asyncio
async def test_postbase_storage_functions_and_events_flow(client, db_session):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": "platform_owner_two",
            "email": "owner2@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}

    owner = (
        await db_session.execute(select(User).where(User.email == "owner2@example.com"))
    ).scalars().first()
    tenant = Tenant(name="Beta", slug="beta", description="Beta tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        TenantMember(
            tenant_id=tenant.id,
            user_id=owner.id,
            role=TenantRole.OWNER,
            is_active=True,
        )
    )
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": "Extended",
            "slug": "extended",
            "description": "Extended capabilities project",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Production", "slug": "prod", "stage": "production"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    anon_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "public_client", "role": "anon"},
    )
    service_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "backend_service", "role": "service_role"},
    )
    assert anon_key_response.status_code == 200, anon_key_response.text
    assert service_key_response.status_code == 200, service_key_response.text
    anon_key = anon_key_response.json()["plaintext_key"]
    service_key = service_key_response.json()["plaintext_key"]

    auth_signup_response = await client.post(
        "/api/v1/auth/users",
        headers={"X-PostBase-Key": anon_key},
        json={
            "username": "cap_user",
            "email": "cap@example.com",
            "password": "CapUser123!",
        },
    )
    assert auth_signup_response.status_code == 200, auth_signup_response.text
    access_token = auth_signup_response.json()["tokens"]["access_token"]
    user_headers = {"Authorization": f"Bearer {access_token}"}

    upload_response = await client.post(
        "/api/v1/storage/files",
        headers=user_headers,
        json={
            "filename": "hello.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"hello postbase").decode("utf-8"),
            "bucket_key": "assets",
            "namespace": "public",
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    file_payload = upload_response.json()
    file_id = file_payload["id"]

    list_files_response = await client.get("/api/v1/storage/files", headers=user_headers)
    assert list_files_response.status_code == 200, list_files_response.text
    assert len(list_files_response.json()) == 1

    signed_url_response = await client.get(
        f"/api/v1/storage/files/{file_id}/signed-url",
        headers=user_headers,
    )
    assert signed_url_response.status_code == 200, signed_url_response.text
    assert "hello.txt" in signed_url_response.json()["url"]

    create_function_response = await client.post(
        "/api/v1/functions",
        headers={"X-PostBase-Key": service_key},
        json={
            "slug": "echoer",
            "name": "Echoer",
            "handler_type": "echo",
            "runtime_profile": "celery-runtime",
        },
    )
    assert create_function_response.status_code == 200, create_function_response.text
    function_id = create_function_response.json()["id"]

    invoke_response = await client.post(
        f"/api/v1/functions/{function_id}/invoke",
        headers=user_headers,
        json={"payload": {"message": "hi"}, "invocation_type": "sync"},
    )
    assert invoke_response.status_code == 200, invoke_response.text
    assert invoke_response.json()["output_json"]["echo"]["message"] == "hi"
    assert invoke_response.json()["retry_count"] == 0

    idempotent_invoke_response = await client.post(
        f"/api/v1/functions/{function_id}/invoke",
        headers={**user_headers, "Idempotency-Key": "invoke-1"},
        json={"payload": {"message": "idempotent"}, "invocation_type": "sync"},
    )
    assert idempotent_invoke_response.status_code == 200, idempotent_invoke_response.text
    replay_invoke_response = await client.post(
        f"/api/v1/functions/{function_id}/invoke",
        headers={**user_headers, "Idempotency-Key": "invoke-1"},
        json={"payload": {"message": "idempotent"}, "invocation_type": "sync"},
    )
    assert replay_invoke_response.status_code == 200, replay_invoke_response.text
    assert replay_invoke_response.json()["replay_of_execution_id"] is not None

    executions_response = await client.get(
        f"/api/v1/functions/{function_id}/executions",
        headers=user_headers,
    )
    assert executions_response.status_code == 200, executions_response.text
    assert len(executions_response.json()) >= 3

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "deployments", "description": "Deployment stream"},
    )
    assert channel_response.status_code == 200, channel_response.text
    channel_id = channel_response.json()["id"]

    subscription_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"target_type": "room", "target_ref": "deployments", "config_json": {}},
    )
    assert subscription_response.status_code == 200, subscription_response.text
    webhook_subscription_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"target_type": "webhook", "target_ref": "https://hooks.example.com/deploy", "config_json": {}},
    )
    assert webhook_subscription_response.status_code == 200, webhook_subscription_response.text

    publish_response = await client.post(
        f"/api/v1/events/publish/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"event_name": "deployment.completed", "payload": {"version": "1.0.0"}},
    )
    assert publish_response.status_code == 200, publish_response.text
    deliveries = publish_response.json()
    assert len(deliveries) == 2
    assert all("attempt_count" in item for item in deliveries)
    assert any(item["status"] == "delivered" for item in deliveries)

    health_response = await client.get(
        f"/api/v1/environments/{environment_id}/reports/capability-health",
        headers=owner_headers,
    )
    assert health_response.status_code == 200, health_response.text
    health_payload = health_response.json()
    assert len(health_payload["bindings"]) >= 5
    assert any(item["capability_key"] == "storage" and item["ready"] for item in health_payload["provider_health"])

    usage_response = await client.get(
        f"/api/v1/projects/{project_id}/usage",
        headers=owner_headers,
    )
    assert usage_response.status_code == 200, usage_response.text
    usage_metrics = {(item["capability_key"], item["metric_key"]) for item in usage_response.json()}
    assert ("storage", "upload_file") in usage_metrics
    assert ("functions", "invoke_function") in usage_metrics
    assert ("events", "publish_event") in usage_metrics

    bindings_response = await client.get(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
    )
    assert bindings_response.status_code == 200, bindings_response.text
    storage_binding = next(item for item in bindings_response.json() if item["capability_key"] == "storage")
    switchover_response = await client.post(
        f"/api/v1/bindings/{storage_binding['id']}/switchovers",
        headers=owner_headers,
        json={"target_provider_key": "s3-compatible", "strategy": "cutover"},
    )
    assert switchover_response.status_code == 200, switchover_response.text
    assert switchover_response.json()["status"] == "pending"
    execute_response = await client.post(
        f"/api/v1/switchovers/{switchover_response.json()['id']}/execute",
        headers=owner_headers,
    )
    assert execute_response.status_code == 200, execute_response.text
    assert execute_response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_postbase_control_plane_lifecycle_management(client, db_session):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": "platform_owner_three",
            "email": "owner3@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}

    owner = (
        await db_session.execute(select(User).where(User.email == "owner3@example.com"))
    ).scalars().first()
    tenant = Tenant(name="Gamma", slug="gamma", description="Gamma tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        TenantMember(
            tenant_id=tenant.id,
            user_id=owner.id,
            role=TenantRole.OWNER,
            is_active=True,
        )
    )
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": "Ops",
            "slug": "ops",
            "description": "Operational management project",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Staging", "slug": "staging", "stage": "staging"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    service_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "ops_service", "role": "service_role"},
    )
    assert service_key_response.status_code == 200, service_key_response.text
    service_key = service_key_response.json()["plaintext_key"]

    secret_response = await client.post(
        f"/api/v1/environments/{environment_id}/secrets",
        headers=owner_headers,
        json={
            "name": "minio",
            "provider_key": "s3-compatible",
            "secret_kind": "access_key",
            "secret_value": "initial-secret-1234",
        },
    )
    assert secret_response.status_code == 201, secret_response.text
    secret_id = secret_response.json()["id"]
    assert secret_response.json()["last_four"] == "1234"

    rotate_response = await client.post(
        f"/api/v1/environments/{environment_id}/secrets/{secret_id}/rotate",
        headers=owner_headers,
        json={"secret_value": "rotated-secret-9876"},
    )
    assert rotate_response.status_code == 200, rotate_response.text
    assert rotate_response.json()["secret"]["last_four"] == "9876"
    assert rotate_response.json()["secret"]["status"] == "active"
    assert rotate_response.json()["rollback_ready"] is True

    webhook_channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "ops-webhooks", "description": "Webhook channel"},
    )
    assert webhook_channel_response.status_code == 200, webhook_channel_response.text
    webhook_channel_id = webhook_channel_response.json()["id"]
    webhook_subscription_response = await client.post(
        f"/api/v1/events/subscriptions/{webhook_channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"target_type": "webhook", "target_ref": "https://hooks.example.com/fail", "config_json": {}},
    )
    assert webhook_subscription_response.status_code == 200, webhook_subscription_response.text
    for _ in range(3):
        publish_webhook_response = await client.post(
            f"/api/v1/events/publish/{webhook_channel_id}",
            headers={"X-PostBase-Key": service_key},
            json={"event_name": "ops.retry.exhausted", "payload": {}},
        )
        assert publish_webhook_response.status_code == 200, publish_webhook_response.text

    webhook_recover_response = await client.post(
        f"/api/v1/environments/{environment_id}/operations/webhooks/recover-exhausted",
        headers=owner_headers,
    )
    assert webhook_recover_response.status_code == 200, webhook_recover_response.text
    assert webhook_recover_response.json()["requeued_jobs"] >= 1

    namespace_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces",
        headers=owner_headers,
        json={"name": "opsdata"},
    )
    assert namespace_response.status_code == 201, namespace_response.text
    namespace_id = namespace_response.json()["id"]
    table_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces/{namespace_id}/tables",
        headers=owner_headers,
        json={
            "table_name": "deployments",
            "columns": [{"name": "id", "type": "uuid", "nullable": False, "primary_key": True}],
            "policy_mode": "authenticated",
        },
    )
    assert table_response.status_code == 201, table_response.text
    migrations_response = await client.get(
        f"/api/v1/environments/{environment_id}/migrations",
        headers=owner_headers,
    )
    assert migrations_response.status_code == 200, migrations_response.text
    rollback_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migrations_response.json()[0]['id']}/cancel",
        headers=owner_headers,
    )
    assert rollback_response.status_code == 200, rollback_response.text
    assert rollback_response.json()["rollback_status"] == "canceled"

    bindings_response = await client.get(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
    )
    assert bindings_response.status_code == 200, bindings_response.text
    events_binding = next(item for item in bindings_response.json() if item["capability_key"] == "events")

    disable_response = await client.post(
        f"/api/v1/bindings/{events_binding['id']}/status",
        headers=owner_headers,
        json={"status": "disabled"},
    )
    assert disable_response.status_code == 200, disable_response.text
    assert disable_response.json()["status"] == "disabled"

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "ops-events", "description": "Ops channel"},
    )
    assert channel_response.status_code == 503, channel_response.text

    health_response = await client.get(
        f"/api/v1/environments/{environment_id}/reports/capability-health",
        headers=owner_headers,
    )
    assert health_response.status_code == 200, health_response.text
    health_payload = health_response.json()
    assert health_payload["overall_ready"] is False
    assert "events" in health_payload["degraded_capabilities"]

    overview_response = await client.get(
        f"/api/v1/projects/{project_id}/overview",
        headers=owner_headers,
    )
    assert overview_response.status_code == 200, overview_response.text
    overview_payload = overview_response.json()
    assert overview_payload["environment_count"] == 1
    assert overview_payload["degraded_bindings"] == 1
    assert overview_payload["secret_count"] == 1
    assert overview_payload["environments"][0]["key_count"] >= 3

    enable_response = await client.post(
        f"/api/v1/bindings/{events_binding['id']}/status",
        headers=owner_headers,
        json={"status": "active"},
    )
    assert enable_response.status_code == 200, enable_response.text
    assert enable_response.json()["status"] == "active"

    second_channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "ops-events", "description": "Ops channel"},
    )
    assert second_channel_response.status_code == 200, second_channel_response.text

    revoke_response = await client.delete(
        f"/api/v1/environments/{environment_id}/secrets/{secret_id}",
        headers=owner_headers,
    )
    assert revoke_response.status_code == 204, revoke_response.text

    secrets_response = await client.get(
        f"/api/v1/environments/{environment_id}/secrets",
        headers=owner_headers,
    )
    assert secrets_response.status_code == 200, secrets_response.text
    assert secrets_response.json()[0]["status"] == "revoked"

    recovered_overview_response = await client.get(
        f"/api/v1/projects/{project_id}/overview",
        headers=owner_headers,
    )
    assert recovered_overview_response.status_code == 200, recovered_overview_response.text
    recovered_payload = recovered_overview_response.json()
    assert recovered_payload["degraded_bindings"] == 0
    assert recovered_payload["secret_count"] == 0


@pytest.mark.asyncio
async def test_postbase_provider_switchovers_to_alternate_adapters(client, db_session):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": "platform_owner_four",
            "email": "owner4@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}

    owner = (
        await db_session.execute(select(User).where(User.email == "owner4@example.com"))
    ).scalars().first()
    tenant = Tenant(name="Delta", slug="delta", description="Delta tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        TenantMember(
            tenant_id=tenant.id,
            user_id=owner.id,
            role=TenantRole.OWNER,
            is_active=True,
        )
    )
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": "Portable",
            "slug": "portable",
            "description": "Provider switchover project",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Runtime", "slug": "runtime", "stage": "development"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    service_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "portable_service", "role": "service_role"},
    )
    anon_key_response = await client.post(
        f"/api/v1/environments/{environment_id}/keys",
        headers=owner_headers,
        json={"name": "portable_anon", "role": "anon"},
    )
    assert service_key_response.status_code == 200, service_key_response.text
    assert anon_key_response.status_code == 200, anon_key_response.text
    service_key = service_key_response.json()["plaintext_key"]
    anon_key = anon_key_response.json()["plaintext_key"]

    bindings_response = await client.get(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
    )
    assert bindings_response.status_code == 200, bindings_response.text
    bindings = {item["capability_key"]: item for item in bindings_response.json()}

    functions_switchover_response = await client.post(
        f"/api/v1/bindings/{bindings['functions']['id']}/switchovers",
        headers=owner_headers,
        json={"target_provider_key": "inline-runtime", "strategy": "cutover"},
    )
    assert functions_switchover_response.status_code == 200, functions_switchover_response.text
    functions_execute_response = await client.post(
        f"/api/v1/switchovers/{functions_switchover_response.json()['id']}/execute",
        headers=owner_headers,
    )
    assert functions_execute_response.status_code == 200, functions_execute_response.text

    storage_switchover_response = await client.post(
        f"/api/v1/bindings/{bindings['storage']['id']}/switchovers",
        headers=owner_headers,
        json={"target_provider_key": "local-disk", "strategy": "cutover"},
    )
    assert storage_switchover_response.status_code == 200, storage_switchover_response.text
    storage_execute_response = await client.post(
        f"/api/v1/switchovers/{storage_switchover_response.json()['id']}/execute",
        headers=owner_headers,
    )
    assert storage_execute_response.status_code == 200, storage_execute_response.text

    events_switchover_response = await client.post(
        f"/api/v1/bindings/{bindings['events']['id']}/switchovers",
        headers=owner_headers,
        json={"target_provider_key": "websocket-gateway", "strategy": "cutover"},
    )
    assert events_switchover_response.status_code == 200, events_switchover_response.text
    events_execute_response = await client.post(
        f"/api/v1/switchovers/{events_switchover_response.json()['id']}/execute",
        headers=owner_headers,
    )
    assert events_execute_response.status_code == 200, events_execute_response.text

    auth_signup_response = await client.post(
        "/api/v1/auth/users",
        headers={"X-PostBase-Key": anon_key},
        json={
            "username": "portable_user",
            "email": "portable@example.com",
            "password": "Portable123!",
        },
    )
    assert auth_signup_response.status_code == 200, auth_signup_response.text
    access_token = auth_signup_response.json()["tokens"]["access_token"]
    user_headers = {"Authorization": f"Bearer {access_token}"}

    upload_response = await client.post(
        "/api/v1/storage/files",
        headers=user_headers,
        json={
            "filename": "portable.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"portable").decode("utf-8"),
            "bucket_key": "artifacts",
            "namespace": "public",
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    assert upload_response.json()["metadata_json"]["storage_provider"] == "local-disk"

    create_function_response = await client.post(
        "/api/v1/functions",
        headers={"X-PostBase-Key": service_key},
        json={
            "slug": "inline_only",
            "name": "Inline Only",
            "handler_type": "echo",
            "runtime_profile": "inline-runtime",
        },
    )
    assert create_function_response.status_code == 200, create_function_response.text
    function_id = create_function_response.json()["id"]

    async_invoke_response = await client.post(
        f"/api/v1/functions/{function_id}/invoke",
        headers=user_headers,
        json={"payload": {"message": "bad"}, "invocation_type": "async"},
    )
    assert async_invoke_response.status_code == 400, async_invoke_response.text

    sync_invoke_response = await client.post(
        f"/api/v1/functions/{function_id}/invoke",
        headers=user_headers,
        json={"payload": {"message": "good"}, "invocation_type": "sync"},
    )
    assert sync_invoke_response.status_code == 200, sync_invoke_response.text
    assert sync_invoke_response.json()["output_json"]["provider"] == "inline-runtime"

    channel_response = await client.post(
        "/api/v1/events/channels",
        headers={"X-PostBase-Key": service_key},
        json={"channel_key": "portable-events", "description": "Portable channel"},
    )
    assert channel_response.status_code == 200, channel_response.text
    channel_id = channel_response.json()["id"]

    subscription_response = await client.post(
        f"/api/v1/events/subscriptions/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"target_type": "room", "target_ref": "portable-room", "config_json": {}},
    )
    assert subscription_response.status_code == 200, subscription_response.text
    assert subscription_response.json()["config_json"]["provider"] == "websocket-gateway"

    publish_response = await client.post(
        f"/api/v1/events/publish/{channel_id}",
        headers={"X-PostBase-Key": service_key},
        json={"event_name": "portable.ready", "payload": {"ok": True}},
    )
    assert publish_response.status_code == 200, publish_response.text
    assert publish_response.json()[0]["status"] == "delivered"

    health_response = await client.get(
        f"/api/v1/environments/{environment_id}/reports/capability-health",
        headers=owner_headers,
    )
    assert health_response.status_code == 200, health_response.text
    health_entries = {item["provider_key"]: item for item in health_response.json()["provider_health"]}
    assert "inline-runtime" in health_entries
    assert "local-disk" in health_entries
    assert "websocket-gateway" in health_entries


async def _setup_migration_context(client, db_session, *, email: str, username: str, tenant_slug: str, project_slug: str):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": username,
            "email": email,
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}
    owner = (await db_session.execute(select(User).where(User.email == email))).scalars().first()
    assert owner is not None

    tenant = Tenant(name=f"{username}-tenant", slug=tenant_slug, description="migration tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": "Migration project",
            "slug": project_slug,
            "description": "Migration checks",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]
    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Staging", "slug": f"{project_slug}-env", "stage": "staging"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]
    namespace_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces",
        headers=owner_headers,
        json={"name": "mig"},
    )
    assert namespace_response.status_code == 201, namespace_response.text
    namespace_id = namespace_response.json()["id"]
    table_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces/{namespace_id}/tables",
        headers=owner_headers,
        json={"table_name": "deployments", "columns": [{"name": "name", "type": "text", "nullable": False}]},
    )
    assert table_response.status_code == 201, table_response.text
    migrations_response = await client.get(f"/api/v1/environments/{environment_id}/migrations", headers=owner_headers)
    assert migrations_response.status_code == 200, migrations_response.text
    return owner_headers, environment_id, migrations_response.json()[0]["id"]


@pytest.mark.asyncio
async def test_migration_apply_success_records_execution(client, db_session):
    owner_headers, environment_id, migration_id = await _setup_migration_context(
        client,
        db_session,
        email="mig-success@example.com",
        username="mig_success",
        tenant_slug="mig-success-tenant",
        project_slug="mig-success-project",
    )
    apply_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply",
        headers=owner_headers,
    )
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["status"] == "applied"

    migration = (await db_session.execute(select(SchemaMigration))).scalars().first()
    execution = (await db_session.execute(select(SchemaMigrationExecution))).scalars().first()
    assert migration is not None
    assert migration.status == MigrationStatus.APPLIED
    assert execution is not None
    assert execution.status == MigrationStatus.APPLIED
    assert execution.finished_at is not None


@pytest.mark.asyncio
async def test_migration_apply_partial_failure_rolls_back_and_records_error(client, db_session, monkeypatch):
    owner_headers, environment_id, migration_id = await _setup_migration_context(
        client,
        db_session,
        email="mig-fail@example.com",
        username="mig_fail",
        tenant_slug="mig-fail-tenant",
        project_slug="mig-fail-project",
    )
    from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider

    original_create_table = PostgresNativeDataProvider.create_table

    async def failing_create_table(self, db, namespace_row, definition):
        await original_create_table(self, db, namespace_row, definition)
        raise RuntimeError("synthetic migration failure")

    monkeypatch.setattr(PostgresNativeDataProvider, "create_table", failing_create_table)
    apply_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply",
        headers=owner_headers,
    )
    assert apply_response.status_code == 500, apply_response.text
    assert "Migration apply failed" in apply_response.json()["detail"]

    migration = (await db_session.execute(select(SchemaMigration))).scalars().first()
    execution = (await db_session.execute(select(SchemaMigrationExecution))).scalars().first()
    assert migration is not None
    assert migration.status == MigrationStatus.FAILED
    assert execution is not None
    assert execution.status == MigrationStatus.FAILED
    assert "synthetic migration failure" in execution.error_text


@pytest.mark.asyncio
async def test_migration_retry_flow_succeeds_after_failure(client, db_session, monkeypatch):
    owner_headers, environment_id, migration_id = await _setup_migration_context(
        client,
        db_session,
        email="mig-retry@example.com",
        username="mig_retry",
        tenant_slug="mig-retry-tenant",
        project_slug="mig-retry-project",
    )
    from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider

    async def always_fail_create_table(self, db, namespace_row, definition):
        raise RuntimeError("retryable synthetic failure")

    monkeypatch.setattr(PostgresNativeDataProvider, "create_table", always_fail_create_table)
    first_apply = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply",
        headers=owner_headers,
    )
    assert first_apply.status_code == 500, first_apply.text

    monkeypatch.undo()
    retry_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/retry",
        headers=owner_headers,
    )
    assert retry_response.status_code == 200, retry_response.text
    assert retry_response.json()["migration"]["status"] == "applied"

    executions = (
        await db_session.execute(select(SchemaMigrationExecution).order_by(SchemaMigrationExecution.id.asc()))
    ).scalars().all()
    assert len(executions) == 2
    assert executions[0].status == MigrationStatus.FAILED
    assert executions[1].status == MigrationStatus.APPLIED


@pytest.mark.asyncio
async def test_migration_reconciliation_no_drift_path(client, db_session):
    owner_headers, environment_id, migration_id = await _setup_migration_context(
        client,
        db_session,
        email="mig-nodrift@example.com",
        username="mig_nodrift",
        tenant_slug="mig-nodrift-tenant",
        project_slug="mig-nodrift-project",
    )
    apply_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply",
        headers=owner_headers,
    )
    assert apply_response.status_code == 200, apply_response.text

    migrations_response = await client.get(
        f"/api/v1/environments/{environment_id}/migrations",
        headers=owner_headers,
    )
    assert migrations_response.status_code == 200, migrations_response.text
    migration_payload = migrations_response.json()[0]
    assert migration_payload["reconciliation_status"] == "in_sync"
    assert migration_payload["drift_severity"] == "none"
    assert migration_payload["affected_entities"] == []


@pytest.mark.asyncio
async def test_migration_reconciliation_detects_table_drift(client, db_session):
    owner_headers, environment_id, migration_id = await _setup_migration_context(
        client,
        db_session,
        email="mig-drift@example.com",
        username="mig_drift",
        tenant_slug="mig-drift-tenant",
        project_slug="mig-drift-project",
    )
    apply_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply",
        headers=owner_headers,
    )
    assert apply_response.status_code == 200, apply_response.text
    migration = await db_session.get(SchemaMigration, int(migration_id))
    assert migration is not None
    namespace = await db_session.get(DataNamespace, migration.namespace_id)
    definition = await db_session.get(TableDefinition, migration.table_definition_id)
    assert namespace is not None
    assert definition is not None
    physical_table_name = f'{namespace.physical_schema}__{definition.table_name}'
    await db_session.execute(text(f'DROP TABLE IF EXISTS "{physical_table_name}"'))
    await db_session.commit()

    migrations_response = await client.get(
        f"/api/v1/environments/{environment_id}/migrations",
        headers=owner_headers,
    )
    assert migrations_response.status_code == 200, migrations_response.text
    payload = migrations_response.json()[0]
    assert payload["reconciliation_status"] == "drifted"
    assert payload["drift_severity"] == "critical"
    assert any(entity.startswith("table:") for entity in payload["affected_entities"])


@pytest.mark.asyncio
async def test_migration_reconciliation_executor_repairs_drift(client, db_session):
    owner_headers, environment_id, migration_id = await _setup_migration_context(
        client,
        db_session,
        email="mig-reconcile-success@example.com",
        username="mig_reconcile_success",
        tenant_slug="mig-reconcile-success-tenant",
        project_slug="mig-reconcile-success-project",
    )
    apply_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply",
        headers=owner_headers,
    )
    assert apply_response.status_code == 200, apply_response.text
    migration = await db_session.get(SchemaMigration, int(migration_id))
    assert migration is not None
    namespace = await db_session.get(DataNamespace, migration.namespace_id)
    definition = await db_session.get(TableDefinition, migration.table_definition_id)
    assert namespace is not None
    assert definition is not None
    physical_table_name = f'{namespace.physical_schema}__{definition.table_name}'
    await db_session.execute(text(f'DROP TABLE IF EXISTS "{physical_table_name}"'))
    await db_session.commit()

    reconcile_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/reconcile",
        headers=owner_headers,
    )
    assert reconcile_response.status_code == 200, reconcile_response.text
    assert reconcile_response.json()["reconciliation_status"] == "in_sync"
    assert reconcile_response.json()["reconcile_attempt_count"] == 1

    second_reconcile_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/reconcile",
        headers=owner_headers,
    )
    assert second_reconcile_response.status_code == 200, second_reconcile_response.text
    assert second_reconcile_response.json()["reconcile_attempt_count"] == 1


@pytest.mark.asyncio
async def test_migration_reconciliation_executor_failure_path(client, db_session, monkeypatch):
    owner_headers, environment_id, migration_id = await _setup_migration_context(
        client,
        db_session,
        email="mig-reconcile-failure@example.com",
        username="mig_reconcile_failure",
        tenant_slug="mig-reconcile-failure-tenant",
        project_slug="mig-reconcile-failure-project",
    )
    apply_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply",
        headers=owner_headers,
    )
    assert apply_response.status_code == 200, apply_response.text
    migration = await db_session.get(SchemaMigration, int(migration_id))
    assert migration is not None
    namespace = await db_session.get(DataNamespace, migration.namespace_id)
    definition = await db_session.get(TableDefinition, migration.table_definition_id)
    assert namespace is not None
    assert definition is not None
    physical_table_name = f'{namespace.physical_schema}__{definition.table_name}'
    await db_session.execute(text(f'DROP TABLE IF EXISTS "{physical_table_name}"'))
    await db_session.commit()

    from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider

    async def failing_create_table(self, db, namespace_row, definition):
        raise RuntimeError("synthetic reconcile failure")

    monkeypatch.setattr(PostgresNativeDataProvider, "create_table", failing_create_table)
    reconcile_response = await client.post(
        f"/api/v1/environments/{environment_id}/migrations/{migration_id}/reconcile",
        headers=owner_headers,
    )
    assert reconcile_response.status_code == 200, reconcile_response.text
    payload = reconcile_response.json()
    assert payload["reconciliation_status"] == "drifted"
    assert payload["reconcile_attempt_count"] == 1
    assert "synthetic reconcile failure" in payload["reconcile_error_text"]


@pytest.mark.asyncio
async def test_control_plane_role_authorization_matrix_for_mutations(client, db_session):
    async def _signup(email: str, username: str) -> tuple[dict[str, str], User]:
        response = await client.post(
            "/api/v1/auth/signup/?set_cookie=false",
            json={
                "username": username,
                "email": email,
                "password": "RoleMatrix123!",
                "confirm_password": "RoleMatrix123!",
            },
        )
        assert response.status_code == 200, response.text
        user = (await db_session.execute(select(User).where(User.email == email))).scalars().first()
        assert user is not None
        return {"Authorization": f"Bearer {response.json()['access']}"}, user

    owner_headers, owner = await _signup("matrix-owner@example.com", "matrix_owner")
    admin_headers, admin = await _signup("matrix-admin@example.com", "matrix_admin")
    member_headers, member = await _signup("matrix-member@example.com", "matrix_member")

    tenant = Tenant(name="Matrix", slug="matrix", description="Role matrix tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add_all(
        [
            TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True),
            TenantMember(tenant_id=tenant.id, user_id=admin.id, role=TenantRole.ADMIN, is_active=True),
            TenantMember(tenant_id=tenant.id, user_id=member.id, role=TenantRole.MEMBER, is_active=True),
        ]
    )
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": "Role matrix project",
            "slug": "role-matrix-project",
            "description": "Role matrix coverage",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Role Matrix Environment", "slug": "role-matrix-env", "stage": "staging"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    bindings_response = await client.get(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
    )
    assert bindings_response.status_code == 200, bindings_response.text
    bindings = bindings_response.json()
    assert bindings
    storage_binding = next(item for item in bindings if item["capability_key"] == "storage")

    namespace_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces",
        headers=owner_headers,
        json={"name": "matrix_ns"},
    )
    assert namespace_response.status_code == 201, namespace_response.text
    namespace_id = namespace_response.json()["id"]
    table_response = await client.post(
        f"/api/v1/environments/{environment_id}/data/namespaces/{namespace_id}/tables",
        headers=owner_headers,
        json={
            "table_name": "matrix_table",
            "columns": [{"name": "id", "type": "text", "nullable": False, "primary_key": True}],
            "policy_mode": "owner_guarded",
            "owner_column": "id",
        },
    )
    assert table_response.status_code == 201, table_response.text
    migrations_response = await client.get(
        f"/api/v1/environments/{environment_id}/migrations",
        headers=owner_headers,
    )
    assert migrations_response.status_code == 200, migrations_response.text
    migration_id = str(migrations_response.json()[0]["id"])
    seed_secret_response = await client.post(
        f"/api/v1/environments/{environment_id}/secrets",
        headers=owner_headers,
        json={
            "name": "matrix-seed-secret",
            "provider_key": "vault",
            "secret_kind": "api_key",
            "secret_value": "matrix-seed-value",
        },
    )
    assert seed_secret_response.status_code == 201, seed_secret_response.text
    seed_secret_id = seed_secret_response.json()["id"]

    role_headers = {"owner": owner_headers, "admin": admin_headers, "member": member_headers}
    mutation_requests = [
        ("bindings", "post", f"/api/v1/environments/{environment_id}/bindings", {"capability_key": "storage", "provider_key": "local-disk", "region": "us-east-1", "config_json": {}, "secret_ref_ids": []}),
        ("secrets", "post", f"/api/v1/environments/{environment_id}/secrets", {"name": "matrix-secret", "provider_key": "vault", "secret_kind": "api_key", "secret_value": "matrix-value"}),
        ("secrets_rotate", "post", f"/api/v1/environments/{environment_id}/secrets/{seed_secret_id}/rotate", {"secret_value": "matrix-updated-value"}),
        ("secrets_revoke", "delete", f"/api/v1/environments/{environment_id}/secrets/{seed_secret_id}", None),
        ("migrations", "post", f"/api/v1/environments/{environment_id}/migrations/{migration_id}/apply", None),
        ("migrations_retry", "post", f"/api/v1/environments/{environment_id}/migrations/{migration_id}/retry", None),
        ("migrations_cancel", "post", f"/api/v1/environments/{environment_id}/migrations/{migration_id}/cancel", None),
        ("switchovers", "post", f"/api/v1/bindings/{storage_binding['id']}/switchovers", {"target_provider_key": "local-disk", "strategy": "cutover"}),
        ("webhook_drain", "post", f"/api/v1/environments/{environment_id}/operations/webhooks/drain", None),
        ("webhook_recover", "post", f"/api/v1/environments/{environment_id}/operations/webhooks/recover-exhausted", None),
    ]

    for role, headers in role_headers.items():
        for _, method, url, payload in mutation_requests:
            response = await getattr(client, method)(url, headers=headers, json=payload)
            if role == "member":
                assert response.status_code == 403, response.text
                detail = response.json()["detail"]
                assert detail["code"] == "control_plane_forbidden"
                assert detail["message"] == "insufficient_role"
                assert detail["required_role"] == "admin"
            else:
                assert response.status_code != 403, response.text


@pytest.mark.asyncio
async def test_binding_status_transition_matrix_enforces_valid_and_invalid_edges(client, db_session):
    async def _setup_environment(email: str, username: str, tenant_slug: str, project_slug: str, env_slug: str):
        signup_response = await client.post(
            "/api/v1/auth/signup/?set_cookie=false",
            json={
                "username": username,
                "email": email,
                "password": "OwnerPass123!",
                "confirm_password": "OwnerPass123!",
            },
        )
        assert signup_response.status_code == 200, signup_response.text
        owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}
        owner = (await db_session.execute(select(User).where(User.email == email))).scalars().first()
        assert owner is not None

        tenant = Tenant(name=f"{username}-tenant", slug=tenant_slug, description="transition tenant", owner_id=owner.id)
        db_session.add(tenant)
        await db_session.flush()
        db_session.add(
            TenantMember(
                tenant_id=tenant.id,
                user_id=owner.id,
                role=TenantRole.OWNER,
                is_active=True,
            )
        )
        await db_session.commit()

        project_response = await client.post(
            "/api/v1/projects",
            headers=owner_headers,
            json={
                "tenant_id": encode_id(tenant.id),
                "name": "Transition project",
                "slug": project_slug,
                "description": "Transition checks",
            },
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        environment_response = await client.post(
            f"/api/v1/projects/{project_id}/environments",
            headers=owner_headers,
            json={"name": "Transition env", "slug": env_slug, "stage": "staging"},
        )
        assert environment_response.status_code == 201, environment_response.text
        return owner_headers, environment_response.json()["id"]

    owner_headers, environment_id = await _setup_environment(
        email="matrix-transition-owner@example.com",
        username="matrix_transition_owner",
        tenant_slug="matrix-transition-tenant",
        project_slug="matrix-transition-project",
        env_slug="matrix-transition-env",
    )

    bindings_response = await client.get(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
    )
    assert bindings_response.status_code == 200, bindings_response.text
    events_binding = next(item for item in bindings_response.json() if item["capability_key"] == "events")

    binding_db_id = next(
        item.id for item in (await db_session.execute(select(CapabilityBinding))).scalars().all() if encode_id(item.id) == events_binding["id"]
    )

    allowed_targets = {
        "pending_validation": {"active", "failed", "disabled"},
        "active": {"deprecated", "failed", "disabled", "retired"},
        "deprecated": {"active", "disabled", "retired"},
        "failed": {"pending_validation", "active", "disabled", "retired"},
        "disabled": {"pending_validation", "active", "retired"},
        "retired": set(),
    }
    states = list(allowed_targets.keys())
    for source in states:
        binding = await db_session.get(CapabilityBinding, binding_db_id)
        assert binding is not None
        binding.status = BindingStatus(source)
        await db_session.commit()
        for target in states:
            if source == target:
                continue
            response = await client.post(
                f"/api/v1/bindings/{events_binding['id']}/status",
                headers=owner_headers,
                json={"status": target, "reason": f"{source}_to_{target}"},
            )
            if target in allowed_targets[source]:
                assert response.status_code == 200, response.text
                payload = response.json()
                assert payload["status"] == target
                assert payload["last_transition_reason"] == f"{source}_to_{target}"
                assert payload["last_transition_actor_user_id"] is not None
                assert payload["last_transition_at"] is not None
            else:
                assert response.status_code == 409, response.text
                detail = response.json()["detail"]
                assert detail["code"] == "binding_invalid_status_transition"
                assert detail["from_status"] == source
                assert detail["to_status"] == target


@pytest.mark.asyncio
async def test_binding_status_transition_uniqueness_and_audit_metadata(client, db_session):
    signup_response = await client.post(
        "/api/v1/auth/signup/?set_cookie=false",
        json={
            "username": "matrix_audit_owner",
            "email": "matrix-audit-owner@example.com",
            "password": "OwnerPass123!",
            "confirm_password": "OwnerPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    owner_headers = {"Authorization": f"Bearer {signup_response.json()['access']}"}
    owner = (await db_session.execute(select(User).where(User.email == "matrix-audit-owner@example.com"))).scalars().first()
    assert owner is not None

    tenant = Tenant(name="audit-tenant", slug="audit-tenant", description="audit tenant", owner_id=owner.id)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role=TenantRole.OWNER, is_active=True))
    await db_session.commit()

    project_response = await client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={
            "tenant_id": encode_id(tenant.id),
            "name": "Audit project",
            "slug": "audit-project",
            "description": "Audit checks",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]
    environment_response = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=owner_headers,
        json={"name": "Audit env", "slug": "audit-env", "stage": "staging"},
    )
    assert environment_response.status_code == 201, environment_response.text
    environment_id = environment_response.json()["id"]

    bindings_response = await client.get(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
    )
    assert bindings_response.status_code == 200, bindings_response.text
    bindings = bindings_response.json()
    storage_binding = next(item for item in bindings if item["capability_key"] == "storage")

    replacement_response = await client.post(
        f"/api/v1/environments/{environment_id}/bindings",
        headers=owner_headers,
        json={
            "capability_key": "storage",
            "provider_key": "s3-compatible",
            "region": "global",
            "config_json": {"bucket": "matrix-bucket"},
            "secret_ref_ids": [],
        },
    )
    assert replacement_response.status_code == 200, replacement_response.text

    activate_old_response = await client.post(
        f"/api/v1/bindings/{storage_binding['id']}/status",
        headers=owner_headers,
        json={"status": "active", "reason": "reactivate old storage"},
    )
    assert activate_old_response.status_code == 409, activate_old_response.text
    detail = activate_old_response.json()["detail"]
    assert detail["code"] == "binding_active_uniqueness_conflict"

    disabled_response = await client.post(
        f"/api/v1/bindings/{storage_binding['id']}/status",
        headers=owner_headers,
        json={"status": "disabled", "reason": "temporary shutdown"},
    )
    assert disabled_response.status_code == 200, disabled_response.text
    payload = disabled_response.json()
    assert payload["last_transition_reason"] == "temporary shutdown"
    assert payload["last_transition_actor_user_id"] is not None
