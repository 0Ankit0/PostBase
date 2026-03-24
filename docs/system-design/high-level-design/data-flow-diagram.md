# Data Flow Diagram - Backend as a Service Platform

```mermaid
flowchart LR
    control[Control Plane UI] --> api[Unified API]
    sdk[App SDK / Client App] --> api
    api --> meta[Metadata and Policy Services]
    api --> auth[Auth Facade]
    api --> data[Postgres Data API]
    api --> storage[Storage Facade]
    api --> fn[Functions and Jobs Facade]
    api --> events[Realtime and Event Facade]
    meta --> pg[(PostgreSQL)]
    data --> pg
    auth --> pg
    storage --> bus[(Message Bus)]
    fn --> bus
    events --> bus
    bus --> adapters[Provider Adapters]
    adapters --> providers[External Providers]
    adapters --> usage[Usage and Audit Projection]
    usage --> report[(Reporting Store)]
```

## Data Flow Notes

1. PostgreSQL stores platform metadata and powers the core data API.
2. Provider-facing capability operations flow through internal facade services and adapters rather than direct client integration.
3. Async tasks such as execution dispatch, event delivery, usage aggregation, and migration work are queue-backed.
