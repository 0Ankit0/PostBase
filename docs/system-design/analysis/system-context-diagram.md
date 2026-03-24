# System Context Diagram - Backend as a Service Platform

```mermaid
flowchart LR
    owners[Project Owners / Tenant Admins]
    developers[App Developers]
    operators[Platform Operators]
    endusers[Application End Users]
    idp[Identity / Auth Providers]
    storage[Storage Providers]
    runtimes[Function / Job Providers]
    events[Realtime / Event Providers]
    accounting[Audit / Analytics / Billing Tools]

    subgraph baas[Backend as a Service Platform]
        control[Control Plane]
        facade[Unified API and SDK]
        adapters[Capability Adapters]
        postgres[Postgres Core]
    end

    owners --> control
    developers --> facade
    operators --> control
    endusers --> facade
    facade --> adapters
    control --> postgres
    adapters --> idp
    adapters --> storage
    adapters --> runtimes
    adapters --> events
    control --> accounting
```

## Context Notes

- Project owners and operators primarily use the control plane to provision projects, configure bindings, and review platform health.
- Developers and downstream applications use the unified facade and should not need provider-specific logic for supported features.
- External providers remain behind adapter boundaries rather than being exposed directly as the platform contract.
