# Staging Validation Evidence (2026-04-09)

> Evidence links point to internal staging artifacts captured during hardening validation.

## Reliability drills

- [EV-REL-001 DB failover + write continuity](https://evidence.postbase.internal/staging/2026-04-09/reliability-db-failover)
- [EV-REL-002 Queue backlog surge + worker recovery](https://evidence.postbase.internal/staging/2026-04-09/reliability-queue-backlog)
- [EV-REL-003 Worker restart replay consistency](https://evidence.postbase.internal/staging/2026-04-09/reliability-worker-restart)
- [EV-REL-004 Switchover rollback control path](https://evidence.postbase.internal/staging/2026-04-09/reliability-switchover-rollback)

## Security drills

- [EV-SEC-101 Secret rotation under load](https://evidence.postbase.internal/staging/2026-04-09/security-secret-rotation-load)
- [EV-SEC-102 Audit integrity checksum validation](https://evidence.postbase.internal/staging/2026-04-09/security-audit-integrity)
- [EV-SEC-103 Tenant-isolation abuse attempts](https://evidence.postbase.internal/staging/2026-04-09/security-tenant-isolation-abuse)
- [EV-SEC-104 Webhook abuse (auth failure + retry exhaustion)](https://evidence.postbase.internal/staging/2026-04-09/security-webhook-abuse)

## Drill scorecards (pass/fail criteria + captured evidence)

| Drill | Pass criteria | Fail criteria | TTD | TTR | Data integrity outcome | Evidence |
|---|---|---|---:|---:|---|---|
| DB failover | Writes resume on promoted node and audit sequence remains monotonic | Any write lost/duplicated after failover | 42s | 4m 18s | No data loss; audit IDs contiguous | EV-REL-001 |
| Queue backlog surge | Backlog alert fires, workers drain queue to steady state, no exhausted-job growth | Backlog age exceeds 15m or dead-letter rate keeps increasing | 1m 05s | 7m 11s | Ordered per-attempt history retained | EV-REL-002 |
| Worker restart recovery | In-flight retrying jobs recovered and resumed within SLO | Jobs stay stuck `retrying` for >10m | 55s | 3m 09s | At-least-once semantics preserved | EV-REL-003 |
| Switchover rollback | Failed switchover returns binding/provider reference to prior active state | Binding remains in invalid provider state | 37s | 2m 44s | Binding and plan history consistent | EV-REL-004 |
| Secret rotation under load | New secret version active with fallback available; no auth outage | Active bindings unresolved or requests fail auth | 49s | 5m 03s | Version chain and fallback validated | EV-SEC-101 |
| Audit integrity checks | Checksum + event-count validation succeed across incident window | Missing/tampered event sequence detected | 31s | 1m 22s | Audit continuity confirmed | EV-SEC-102 |
| Tenant-isolation abuse | Cross-tenant secret/binding attempts rejected with no side effects | Any unauthorized cross-tenant association succeeds | 18s | 1m 07s | No boundary leakage observed | EV-SEC-103 |
| Webhook abuse scenarios | Auth anomalies detected, retry ceiling/dead-letter applied, circuit-break behavior verified | Unbounded retries or silent delivery/auth failures | 26s | 2m 58s | No duplicate state mutations | EV-SEC-104 |

## Alert thresholds used during drills

- `webhook_backlog_alert_total`: trigger when pending+retrying queue depth ≥ **150**.
- `webhook_delivery_failure_alert_total`: trigger when dead-lettered jobs ≥ **25**.
- `webhook_auth_anomaly_total`: trigger when webhook auth failures ≥ **3**.
- Webhook timeout budget: **5000ms**; retries bounded by `POSTBASE_WEBHOOK_RETRY_CEILING` (**6**).

## Definition of done status

- ✅ Critical failure scenarios are recoverable via documented/tested procedures.
- ✅ Security controls were exercised in live drills, not only design review.
- ✅ Alerts and dashboard counters were actionable during incident simulation windows.

---

# Staging Validation Evidence (2026-04-08)

> Historical validation set retained for reference.

- [EV-SEC-001 Secret rotation failure drill](https://evidence.postbase.internal/staging/2026-04-08/secret-rotation-failure)
- [EV-SEC-002 Provider switchover audit continuity](https://evidence.postbase.internal/staging/2026-04-08/switchover-audit)
- [EV-SEC-003 Tenant-boundary enforcement regression](https://evidence.postbase.internal/staging/2026-04-08/tenant-boundary)
- [EV-PROV-001 Provider compatibility guardrail](https://evidence.postbase.internal/staging/2026-04-08/provider-compatibility)
- [EV-PROV-002 Missing secret pending-validation path](https://evidence.postbase.internal/staging/2026-04-08/provider-secret-readiness)
- [EV-PROV-003 Regional compatibility validation](https://evidence.postbase.internal/staging/2026-04-08/provider-region)
- [EV-PROV-004 Planned switchover prerequisite checks](https://evidence.postbase.internal/staging/2026-04-08/provider-switchover-plan)
- [EV-PROV-005 Deprecated adapter replacement rehearsal](https://evidence.postbase.internal/staging/2026-04-08/provider-deprecation)
- [EV-OPS-001 Metadata failover replay](https://evidence.postbase.internal/staging/2026-04-08/ops-metadata-failover)
- [EV-OPS-002 Queue backlog recovery](https://evidence.postbase.internal/staging/2026-04-08/ops-queue-backlog)
- [EV-OPS-003 Binding health degradation signal](https://evidence.postbase.internal/staging/2026-04-08/ops-binding-health)
- [EV-OPS-004 Reporting freshness marker check](https://evidence.postbase.internal/staging/2026-04-08/ops-reporting-freshness)
- [EV-OPS-005 Partial rollback recovery workflow](https://evidence.postbase.internal/staging/2026-04-08/ops-switchover-rollback)
