# Architecture Diagram - Backend as a Service Platform

```mermaid
flowchart TB
    subgraph access[Access Channels]
        control[Control Plane UI]
        sdk[Developer SDK and Client Apps]
        admin[Operator and Security Consoles]
    end

    subgraph platform[Core Platform]
        gateway[API Gateway]
        authz[Identity and Access Control]
        projects[Project and Environment Service]
        bindings[Capability Binding Service]
        auth[Auth Facade Service]
        data[Postgres Data API Service]
        storage[Storage Facade Service]
        functions[Functions and Jobs Facade]
        events[Realtime and Events Facade]
        secrets[Secrets and Config Service]
        migration[Migration and Switchover Orchestrator]
        reporting[Usage, Audit, and Reporting Service]
    end

    subgraph execution[Execution and Integration Layer]
        workers[Background Workers]
        registry[Adapter Registry]
        adapters[Capability Adapter Runtimes]
    end

    subgraph data[State and Data Layer]
        pg[(PostgreSQL)]
        queue[(Message Bus)]
        report[(Reporting Store)]
        vault[(Secret Store)]
    end

    control --> gateway
    sdk --> gateway
    admin --> gateway
    gateway --> authz
    gateway --> projects
    gateway --> bindings
    gateway --> auth
    gateway --> data
    gateway --> storage
    gateway --> functions
    gateway --> events
    gateway --> secrets
    gateway --> migration
    gateway --> reporting
    projects --> pg
    bindings --> pg
    auth --> pg
    data --> pg
    reporting --> pg
    secrets --> vault
    storage --> queue
    functions --> queue
    events --> queue
    migration --> queue
    queue --> workers
    workers --> registry
    registry --> adapters
    reporting --> report
```

## Responsibilities

| Component | Responsibility |
|-----------|----------------|
| Project and Environment Service | Provision tenants, projects, environments, and lifecycle state |
| Capability Binding Service | Attach providers to capabilities with compatibility validation |
| Auth Facade Service | Stable identity, session, and token semantics |
| Postgres Data API Service | Schema-aware data access and migration tracking |
| Storage Facade Service | File abstraction, metadata, uploads, downloads, access grants |
| Functions and Jobs Facade | Deploy, invoke, schedule, and track executions |
| Realtime and Events Facade | Channels, subscriptions, event fanout, webhook semantics |
| Migration and Switchover Orchestrator | Provider change plans, cutover, rollback, and auditability |
| Adapter Registry | Adapter catalog, certification state, compatibility profiles |
