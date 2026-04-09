# Deployment Diagram - Backend as a Service Platform

```mermaid
flowchart TB
    subgraph edgeZone[Edge Zone]
        internet[Internet / SDK Clients] --> edge[WAF + Rate Limit + TLS Edge]
        ops[Operator Access] --> adminAccess[Admin Access Gateway]
    end

    subgraph appZone[App Zone]
        api[API Runtime Pool]
        ws[Realtime Gateway Pool]
        workers[Async Worker Pool]
        migration[Migration / Orchestration Workers]
    end

    subgraph dataZone[Data Zone]
        db[(Managed PostgreSQL)]
        queue[(Managed Queue / Bus)]
        vault[(Managed Secret Store)]
        report[(Metrics / Logs / Reporting Store)]
    end

    subgraph integrationZone[Integration / Controlled Egress Zone]
        egress[Outbound Egress Gateway]
        providers[External Provider Networks]
    end

    edge --> api
    edge --> ws
    adminAccess --> api
    api --> queue
    api --> db
    api --> vault
    api --> report
    ws --> queue
    ws --> report
    workers --> queue
    workers --> db
    workers --> vault
    workers --> report
    migration --> queue
    migration --> db
    migration --> vault
    workers --> egress
    migration --> egress
    egress --> providers
```

## Deployment Notes

- API, realtime gateway, and async workers run as separate workload pools with independent autoscaling and resource quotas.
- Realtime burst handling must not consume worker capacity reserved for queue drains, migrations, or webhook delivery.
- PostgreSQL is a critical tier for metadata and core data services and stays private to app-zone callers.
- Provider-facing adapter traffic originates only from approved worker runtimes through controlled egress paths.
