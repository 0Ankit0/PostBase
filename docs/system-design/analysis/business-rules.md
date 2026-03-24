# Business Rules - Backend as a Service Platform

## Postgres Core Rules
- PostgreSQL is mandatory for platform metadata and the v1 data API model.
- Projects cannot activate data capabilities without a valid Postgres environment and schema metadata.
- Schema migrations must be recorded and associated with environment and actor context.

## Adapter and Binding Rules
- Only certified adapter versions may be bound to production environments.
- An environment may have only one active provider binding per capability type at a time.
- Provider switchovers must pass compatibility checks before cutover begins.

## Migration Rules

| Rule Area | Baseline Rule |
|-----------|---------------|
| Switchover planning | Every provider change requires a tracked switchover plan |
| Secret readiness | Target provider secrets must validate before migration can start |
| Cutover | Cutover must be explicit and auditable |
| Rollback | Rollback path must be defined before activating production switchover |
| Deprecation | Old bindings may remain readable until retirement policy is satisfied |

## Tenant and Security Rules
- Tenant boundaries must be enforced for every project, environment, secret, and capability record.
- Secret material must never be returned directly through normal operational APIs.
- Privileged actions such as provider changes, schema changes, and certificate updates require audit logs.

## SDK and Facade Rules
- Stable facade semantics must be preserved even if providers differ in optional behavior.
- Provider-specific behavior may surface only through documented capability flags or compatibility notes.
- Unsupported provider-specific custom logic must not silently bypass facade contracts.
