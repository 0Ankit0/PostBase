# ERD and Database Schema - Backend as a Service Platform

```mermaid
erDiagram
    TENANT ||--o{ PROJECT : owns
    PROJECT ||--o{ ENVIRONMENT : contains
    ENVIRONMENT ||--o{ CAPABILITY_BINDING : activates
    CAPABILITY_TYPE ||--o{ PROVIDER_CATALOG_ENTRY : categorizes
    PROVIDER_CATALOG_ENTRY ||--o{ CAPABILITY_BINDING : backs
    CAPABILITY_BINDING ||--o{ SWITCHOVER_PLAN : changes
    ENVIRONMENT ||--o{ SECRET_REF : stores
    PROJECT ||--o{ AUTH_USER : manages
    AUTH_USER ||--o{ SESSION_RECORD : issues
    ENVIRONMENT ||--o{ DATA_NAMESPACE : hosts
    DATA_NAMESPACE ||--o{ TABLE_DEFINITION : defines
    ENVIRONMENT ||--o{ FILE_OBJECT : tracks
    ENVIRONMENT ||--o{ FUNCTION_DEFINITION : deploys
    FUNCTION_DEFINITION ||--o{ EXECUTION_RECORD : runs
    ENVIRONMENT ||--o{ EVENT_CHANNEL : exposes
    EVENT_CHANNEL ||--o{ SUBSCRIPTION : binds
    ENVIRONMENT ||--o{ USAGE_METER : measures
    PROJECT ||--o{ AUDIT_LOG : records
```

## Table Notes

| Table | Notes |
|-------|-------|
| tenants | Customer boundary and plan context |
| projects | Logical app workspaces |
| environments | Dev/staging/prod or tenant-defined stages |
| capability_bindings | Active capability-to-provider relationships |
| provider_catalog_entries | Certified adapter versions and provider metadata |
| switchover_plans | Provider migration orchestration records |
| secret_refs | Secret references, not raw secret material |
| auth_users | Auth facade user identities |
| session_records | Session lifecycle and token state |
| data_namespaces | Schema-scoped data API metadata |
| table_definitions | Table metadata and policy configuration |
| file_objects | Provider-independent storage metadata |
| function_definitions | Deployed function or job descriptors |
| execution_records | Invocation history |
| event_channels | Realtime or messaging namespaces |
| subscriptions | Webhook, event, or channel subscribers |
| usage_meters | Usage measurements by capability |
| audit_logs | Immutable operational history |
