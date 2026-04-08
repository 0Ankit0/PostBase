# ERD and Database Schema - Backend as a Service Platform

```mermaid
erDiagram
    TENANT ||--o{ PROJECT : owns
    PROJECT ||--o{ ENVIRONMENT : contains

    CAPABILITY_TYPE ||--o{ PROVIDER_CATALOG_ENTRY : categorizes
    ENVIRONMENT ||--o{ CAPABILITY_BINDING : activates
    PROVIDER_CATALOG_ENTRY ||--o{ CAPABILITY_BINDING : backs
    CAPABILITY_BINDING ||--o{ SWITCHOVER_PLAN : changes

    ENVIRONMENT ||--o{ SECRET_REF : stores
    CAPABILITY_BINDING ||--o{ BINDING_SECRET_REF : links
    SECRET_REF ||--o{ BINDING_SECRET_REF : referenced_by

    ENVIRONMENT ||--o{ ENVIRONMENT_API_KEY : issues

    PROJECT ||--o{ AUTH_USER : manages
    ENVIRONMENT ||--o{ AUTH_USER : scopes
    AUTH_USER ||--o{ SESSION_RECORD : issues

    ENVIRONMENT ||--o{ DATA_NAMESPACE : hosts
    DATA_NAMESPACE ||--o{ TABLE_DEFINITION : defines
    TABLE_DEFINITION ||--o{ POLICY_DEFINITION : governs
    ENVIRONMENT ||--o{ SCHEMA_MIGRATION : tracks

    ENVIRONMENT ||--o{ FILE_OBJECT : tracks

    ENVIRONMENT ||--o{ FUNCTION_DEFINITION : deploys
    FUNCTION_DEFINITION ||--o{ EXECUTION_RECORD : runs

    ENVIRONMENT ||--o{ EVENT_CHANNEL : exposes
    EVENT_CHANNEL ||--o{ SUBSCRIPTION : binds
    EVENT_CHANNEL ||--o{ DELIVERY_RECORD : emits
    SUBSCRIPTION ||--o{ DELIVERY_RECORD : receives
    EVENT_CHANNEL ||--o{ WEBHOOK_DELIVERY_JOB : queues
    SUBSCRIPTION ||--o{ WEBHOOK_DELIVERY_JOB : targets

    ENVIRONMENT ||--o{ USAGE_METER : measures
    PROJECT ||--o{ AUDIT_LOG : records
```

## Table Notes

| Table | Notes |
|-------|-------|
| `postbase_project` | Logical app workspaces under a tenant |
| `postbase_environment` | Dev/staging/prod or tenant-defined stages |
| `postbase_capability_type` | Capability taxonomy (`auth`, `data`, `storage`, `functions`, `events`) |
| `postbase_provider_catalog_entry` | Certified adapter versions and provider metadata |
| `postbase_capability_binding` | Active capability-to-provider relationships |
| `postbase_switchover_plan` | Provider migration orchestration records |
| `postbase_secret_ref` | Secret references, not raw secret material |
| `postbase_binding_secret_ref` | Many-to-many link between bindings and secret refs |
| `postbase_environment_api_key` | Environment-scoped machine credentials |
| `postbase_auth_user` | Auth facade user identities |
| `postbase_session_record` | Session lifecycle and token state |
| `postbase_data_namespace` | Schema-scoped data API metadata |
| `postbase_table_definition` | Table metadata and policy configuration |
| `postbase_policy_definition` | Policy config attached to table definitions |
| `postbase_schema_migration` | Migration/apply ledger for namespaces/tables |
| `postbase_file_object` | Provider-independent storage metadata |
| `postbase_function_definition` | Deployed function or job descriptors |
| `postbase_execution_record` | Invocation history |
| `postbase_event_channel` | Realtime or messaging namespaces |
| `postbase_subscription` | Webhook/event subscribers |
| `postbase_delivery_record` | Event delivery attempts/history |
| `postbase_webhook_delivery_job` | Durable webhook retry queue |
| `postbase_usage_meter` | Usage measurements by capability |
| `postbase_audit_log` | Immutable operational history |
