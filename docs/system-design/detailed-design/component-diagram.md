# Component Diagram - Backend as a Service Platform

```mermaid
flowchart LR
    clients[Control Plane / SDK / Apps] --> api[API Layer]
    api --> authz[Access Control Component]
    api --> projects[Project and Environment Component]
    api --> bindings[Capability Binding Component]
    api --> auth[Auth Facade Component]
    api --> data[Postgres Data API Component]
    api --> storage[Storage Facade Component]
    api --> functions[Functions and Jobs Component]
    api --> events[Realtime and Events Component]
    api --> secrets[Secrets and Config Component]
    api --> migration[Switchover Component]
    api --> reporting[Usage and Audit Component]
    bindings --> migration
    storage --> reporting
    functions --> reporting
    events --> reporting
```

## Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| Access Control | Tenant, project, environment, and role scoping |
| Project and Environment | Provisioning and lifecycle state |
| Capability Binding | Provider selection and compatibility checks |
| Auth Facade | Identity and session abstraction |
| Postgres Data API | Schema-aware CRUD and policy mediation |
| Storage Facade | Files, buckets, metadata, signed access |
| Functions and Jobs | Deployments, schedules, executions |
| Realtime and Events | Channels, subscriptions, fanout, webhooks |
| Secrets and Config | Secret references, provider config, rotations |
| Switchover | Migration plans, cutover, rollback |
| Usage and Audit | Metering, operational visibility, immutable history |
