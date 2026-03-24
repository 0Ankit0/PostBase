# Deployment Diagram - Backend as a Service Platform

```mermaid
flowchart TB
    internet[Internet / SDK Clients] --> edge[WAF / API Edge]
    ops[Operator Access] --> adminAccess[Admin Access Gateway]
    edge --> api[Unified API Cluster]
    edge --> ws[Realtime Gateway]
    adminAccess --> api
    api --> workers[Worker Cluster]
    api --> db[(Managed PostgreSQL)]
    api --> queue[(Managed Queue / Bus)]
    api --> report[(Reporting Store)]
    api --> vault[(Secret Store)]
    workers --> db
    workers --> queue
    workers --> report
    workers --> vault
    workers --> providers[External Provider Networks]
```

## Deployment Notes

- Separate API, realtime gateway, and worker concerns so bursty client activity does not starve orchestration tasks.
- PostgreSQL should be treated as a critical tier for metadata and core data services.
- Provider-facing adapter traffic should originate from controlled worker or adapter runtimes with explicit secret access.
