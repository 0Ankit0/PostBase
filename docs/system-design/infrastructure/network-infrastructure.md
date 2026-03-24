# Network Infrastructure - Backend as a Service Platform

## Network Zones

| Zone | Purpose | Key Controls |
|------|---------|--------------|
| Public API Edge | SDK/client access and control-plane access | TLS termination, WAF, rate limiting |
| Admin Access | Operator and security admin workflows | MFA/SSO, zero-trust or private access |
| Application Zone | API, realtime gateways, workers, orchestration | Private subnets, service identity, secrets management |
| Data Zone | PostgreSQL, reporting store, secret store, queue | No public access, encryption, network segmentation |
| Integration Zone | External providers and package backends | Outbound allow-list, egress controls, credential rotation |

## Traffic Principles

- Client traffic should never call provider APIs directly when facade semantics are required.
- Secret-bearing traffic should be isolated to approved runtime components.
- Switchover and migration workflows should be observable and interruptible without breaking control-plane safety.
