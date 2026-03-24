# API Design - Backend as a Service Platform

## API Style
- RESTful JSON APIs with tenant, project, and environment scoping.
- WebSocket or event-stream endpoints for realtime/event use cases.
- Cursor pagination for operational collections such as projects, files, executions, subscriptions, and audit logs.
- Idempotency keys for provisioning, binding changes, file writes, function deployment, and migration triggers.

## Core Endpoints

| Area | Method | Endpoint | Purpose |
|------|--------|----------|---------|
| Projects | POST | `/api/v1/projects` | Create project |
| Environments | POST | `/api/v1/projects/{projectId}/environments` | Create environment |
| Providers | GET | `/api/v1/provider-catalog` | List certified adapter options |
| Bindings | POST | `/api/v1/environments/{envId}/bindings` | Bind provider to capability |
| Bindings | POST | `/api/v1/bindings/{bindingId}/switchovers` | Start provider switchover |
| Auth | POST | `/api/v1/auth/users` | Create auth user through facade |
| Auth | POST | `/api/v1/auth/sessions` | Create session or token |
| Data | POST | `/api/v1/data/namespaces` | Create namespace / schema scope |
| Data | POST | `/api/v1/data/tables` | Register or apply table definition |
| Data | POST | `/api/v1/data/query` | Facade query endpoint |
| Storage | POST | `/api/v1/storage/files` | Create upload intent / file record |
| Functions | POST | `/api/v1/functions` | Register function or job |
| Functions | POST | `/api/v1/functions/{fnId}/invoke` | Invoke function |
| Events | POST | `/api/v1/events/subscriptions` | Create realtime or webhook subscription |
| Admin | POST | `/api/v1/admin/secrets` | Register or rotate secret reference |
| Reports | GET | `/api/v1/reports/capability-health` | Capability usage and health summary |

## Example: Capability Binding Request

```json
{
  "environmentId": "env_prod_01",
  "capabilityKey": "storage",
  "providerKey": "aws-s3",
  "adapterVersion": "1.4.0",
  "secretRefIds": ["sec_storage_prod"],
  "config": {
    "bucket": "project-prod-assets",
    "region": "ap-south-1"
  }
}
```

## Example: Switchover Request

```json
{
  "bindingId": "bind_storage_prod",
  "targetProviderKey": "digitalocean-spaces",
  "targetAdapterVersion": "1.2.0",
  "strategy": "copy-then-cutover",
  "requestedBy": "usr_owner_44"
}
```

## Authorization Notes
- Project owners and operators can create or change bindings subject to role policy.
- App-facing auth, data, storage, function, and event APIs are always resolved through environment-scoped facade contracts.
- Secret creation, provider switchover, and cross-environment operations require elevated permissions and audit logging.
