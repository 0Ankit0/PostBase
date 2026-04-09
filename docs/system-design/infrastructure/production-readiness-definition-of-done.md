# Production Topology Hardening - Definition of Done

## Scope

This checklist is the acceptance gate for production topology provisioning and staging parity confidence.

## Hard Requirements

1. Provision production-like topology with explicit **edge**, **app**, **data**, and **integration/egress** boundaries.
2. Enforce security controls:
   - TLS termination at edge.
   - WAF + rate-limit at edge.
   - Private data plane for stateful services.
   - Least-privilege service-to-service and secret access.
3. Separate runtime workloads:
   - API runtime pool.
   - Realtime gateway pool.
   - Async worker pools (including migration/reconciliation).
4. Configure managed dependencies:
   - Database, queue, secret store, and metrics/logging.
   - Backup/restore mechanisms configured and tested.
   - Retention windows defined and policy-aligned.
5. Validate staging mirrors production architecture for realistic operational drills.

## Validation Evidence Required

| Requirement | Evidence Type | Pass Criteria |
|-------------|---------------|---------------|
| No insecure/public data plane | Network policy snapshot + endpoint scan | DB/queue/secret services are private-only with no direct public ingress |
| Edge security controls enforced | Edge config export + synthetic test | TLS policy, WAF rules, and rate-limits are active and tested |
| Workload isolation holds under load | Load test report + autoscaling logs | API/realtime spikes do not starve worker throughput or migration SLAs |
| Managed dependency resilience | Backup job history + restore drill report | Successful restore and replay drills in both staging and production windows |
| Staging production parity | Topology diff report + drill checklist | No material architecture drift that would invalidate incident rehearsal confidence |

## Definition of Done

- No critical service depends on insecure or publicly exposed data-plane access.
- Workload isolation and scaling behavior are validated under representative load.
- Staging is a trustworthy rehearsal environment for production operations and incidents.
