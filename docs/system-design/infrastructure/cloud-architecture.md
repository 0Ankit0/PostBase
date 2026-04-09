# Cloud Architecture - Backend as a Service Platform

## Reference Cloud Mapping (AWS Example)

| Capability | Reference Service |
|------------|-------------------|
| Public edge | CloudFront / ALB + AWS WAF |
| API and realtime gateway | ECS/Fargate or EKS |
| Worker fleet | ECS/Fargate, EKS jobs, or queue workers |
| PostgreSQL | Amazon RDS for PostgreSQL |
| Messaging / queue | Amazon SQS / EventBridge |
| Secret storage | AWS Secrets Manager / HashiCorp Vault |
| Reporting store | Redshift / RDS replica / analytics warehouse |
| Monitoring | CloudWatch + OpenTelemetry |
| Identity federation | IAM Identity Center / external IdP |

## Managed Dependency Baseline (Production and Staging)

| Dependency | Baseline | Backup / Restore | Retention Policy |
|------------|----------|------------------|------------------|
| PostgreSQL metadata + tenant data | Multi-AZ managed Postgres with private endpoints | Point-in-time recovery + scheduled snapshots; quarterly restore drill | Transaction logs and snapshots retained per compliance class (for example: 35-90 days) |
| Queue / bus | Managed queue with DLQ + replay tooling | Message replay from DLQ and archived payload store | Primary queue visibility-timeout windows + DLQ retention (for example: 14 days) |
| Secret store | Managed secret vault with versioned secrets | Version rollback and cross-region backup where available | Secret versions retained until rotation + audit requirements are met |
| Metrics / logs / traces | Centralized telemetry pipeline | Immutable archive export and periodic restore/read tests | Hot retention for operations + longer cold archive retention (for example: 30 days hot / 365 days archive) |

## Runtime Isolation and Scaling Controls

- API runtime pool: latency-sensitive synchronous control-plane and facade requests.
- Realtime gateway pool: persistent connection fan-out and subscription traffic.
- Async worker pools: queue consumers, delivery jobs, migration jobs, and reconciliation loops.
- Each pool uses separate autoscaling signals (RPS/CPU for API, connections/events for realtime, queue depth/lag for workers).
- Apply minimum reserved capacity for worker and migration pools so API/realtime traffic spikes cannot starve critical async tasks.

## Architecture Notes

- The control plane can run in one cloud while adapters target multiple supported providers.
- Production environments should isolate secret domains, project metadata, and provider egress policies carefully.
- Switchover workflows may require temporary dual-writes, copy jobs, or migration runners depending on capability type.

## Staging Parity Validation

Staging must mirror the production topology closely enough to trust operational drills:

1. Same zone model: edge, app, data, and integration/egress boundaries.
2. Same security controls class: edge TLS/WAF/rate-limiting, private data plane, and workload-scoped identities.
3. Same workload decomposition: API, realtime, and async workers isolated with independent scaling policies.
4. Same dependency class: managed DB, queue, secret store, and telemetry services with backup/restore checks enabled.
5. Same runbook drills: failover, restore, queue backlog, egress-policy enforcement, and incident observability rehearsed in staging before production changes.
