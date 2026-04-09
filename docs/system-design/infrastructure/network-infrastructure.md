# Network Infrastructure - Backend as a Service Platform

## Production-like Zone Topology

| Zone | Purpose | Allowed Inbound | Allowed Outbound | Required Controls |
|------|---------|-----------------|------------------|-------------------|
| Edge Zone | Public SDK/client entry and protected operator ingress | Internet HTTPS only (443) | Application zone entrypoints only | TLS termination, WAF, rate-limits, bot/abuse protections |
| App Zone | API, realtime gateway, and async worker runtimes | Edge zone and approved internal service-to-service traffic | Data zone and integration egress gateways only | Private subnets, mutual service auth, least-privilege IAM, runtime isolation |
| Data Zone | Managed stateful dependencies (DB, queue, secret store, telemetry sinks) | App zone only | Backup targets and approved observability exporters only | No public exposure, at-rest encryption, in-transit TLS, policy-based access |
| Integration / Egress Zone | Controlled outbound path to third-party providers and webhooks | App zone only via egress brokers/NAT | Explicitly allow-listed external endpoints only | Domain/IP allow-listing, egress audit logging, credential scoping + rotation |
| Admin Access Plane | Operator and security admin workflows | Corporate identity and managed admin ingress only | App zone control-plane APIs only | MFA/SSO, short-lived sessions, approval workflows, just-in-time access |

## Data-plane Security Rules

1. **No public data plane:** databases, queues, secret stores, and internal event streams are reachable only from private app subnets.
2. **End-to-end encryption:** TLS is enforced at edge and for east-west service traffic where supported.
3. **Least privilege identities:** each runtime workload gets its own service identity, role, and secrets scope.
4. **Controlled egress:** provider and webhook traffic exits through dedicated integration boundaries, never directly from arbitrary workloads.

## Traffic Principles

- Client traffic never bypasses the edge controls to reach app or data zones.
- Secret-bearing traffic is isolated to approved runtime components and secret retrieval paths.
- Switchover and migration workflows remain observable and interruptible without breaking control-plane safety.
