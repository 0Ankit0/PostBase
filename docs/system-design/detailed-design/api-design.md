# API Design - Backend as a Service Platform

## API Style
- RESTful JSON APIs with tenant, project, and environment scoping.
- WebSocket or event-stream endpoints for realtime/event use cases.
- Cursor pagination is **currently partial**: project listing is paginated, while most other list endpoints return arrays.
- Idempotency keys are implemented for function invocation (`Idempotency-Key` header); broader idempotency coverage remains planned.

## Core Endpoints (Conformed to Current Backend)

> Note: Paths below are shown as `/api/v1/...` for public API shape. Backend router modules define relative paths that are mounted under the versioned prefix.

### Control plane

| Area | Method | Endpoint | Purpose |
|------|--------|----------|---------|
| Projects | POST | `/api/v1/projects` | Create project |
| Projects | GET | `/api/v1/projects` | List projects visible to caller |
| Environments | POST | `/api/v1/projects/{projectId}/environments` | Create environment |
| Environments | GET | `/api/v1/projects/{projectId}/environments` | List project environments |
| Providers | GET | `/api/v1/provider-catalog` | List certified adapter options |
| Bindings | GET | `/api/v1/environments/{envId}/bindings` | List environment bindings |
| Bindings | POST | `/api/v1/environments/{envId}/bindings` | Create binding version |
| Bindings | POST | `/api/v1/bindings/{bindingId}/switchovers` | Create switchover plan |
| Switchovers | POST | `/api/v1/switchovers/{switchoverId}/execute` | Execute switchover plan |
| Switchovers | GET | `/api/v1/bindings/{bindingId}/switchovers` | List binding switchovers |
| Secrets | GET | `/api/v1/environments/{envId}/secrets` | List environment secret refs |
| Secrets | POST | `/api/v1/environments/{envId}/secrets` | Create environment secret ref |
| Secrets | POST | `/api/v1/environments/{envId}/secrets/{secretId}/rotate` | Rotate secret value |
| Data control-plane | POST | `/api/v1/environments/{envId}/data/namespaces` | Create namespace metadata |
| Data control-plane | POST | `/api/v1/environments/{envId}/data/namespaces/{namespaceId}/tables` | Create table metadata |
| Migrations | GET | `/api/v1/environments/{envId}/migrations` | List environment migrations |
| Migrations | POST | `/api/v1/environments/{envId}/migrations/{migrationId}/apply` | Apply migration |
| Reports | GET | `/api/v1/environments/{envId}/reports/capability-health` | Capability usage and health summary |

### Capability facade

| Area | Method | Endpoint | Purpose |
|------|--------|----------|---------|
| Auth | POST | `/api/v1/auth/users` | Create auth user through facade |
| Auth | POST | `/api/v1/auth/sessions` | Create session/token pair |
| Auth | POST | `/api/v1/auth/sessions/refresh` | Refresh auth tokens |
| Auth | GET | `/api/v1/auth/me` | Retrieve current auth user |
| Data | POST | `/api/v1/data/query` | Facade query endpoint |
| Data | GET | `/api/v1/data/{namespace}/{table}` | List rows |
| Storage | POST | `/api/v1/storage/files` | Create upload intent / file record |
| Functions | POST | `/api/v1/functions` | Register function or job |
| Functions | POST | `/api/v1/functions/{functionId}/invoke` | Invoke function |
| Events | POST | `/api/v1/events/channels` | Create event channel |
| Events | POST | `/api/v1/events/subscriptions/{channelId}` | Create channel subscription |
| Events | POST | `/api/v1/events/publish/{channelId}` | Publish event |

## Example: Capability Binding Request

```json
{
  "environmentId": "env_prod_01",
  "capabilityKey": "storage",
  "providerKey": "aws-s3",
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
  "strategy": "copy-then-cutover"
}
```

## Example: Data Query Request

```json
{
  "namespace": "app",
  "table": "posts",
  "filters": {
    "status": "published"
  },
  "limit": 25,
  "offset": 0,
  "order_by": "id",
  "order_direction": "desc"
}
```

## Authorization Notes
- Project owners and operators can create or change bindings subject to role policy.
- App-facing auth, data, storage, function, and event APIs are resolved through environment-scoped facade contracts.
- Secret creation, provider switchover, and cross-environment operations require elevated permissions and audit logging.
- Tenant invitation APIs are owned by the multitenancy/iam surface and are tracked outside PostBase capability/control-plane modules.
