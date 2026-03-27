# PostBase Parity Implementation Checklist

This checklist translates the parity matrix into execution-ready tasks. Status values:

- [x] done
- [~] in progress
- [ ] pending

## Phase 1 — Docs and Validation Baseline

- [x] Canonical docs index at `docs/README.md`.
- [x] Top-level README aligned to PostBase repo layout.
- [x] Docs validator checks `docs/system-design` structure and parity markers.
- [x] Parity matrix maintained as canonical implementation status tracker.

## Phase 2 — Backend Control-Plane Foundation

- [x] Environment operational metadata (`region_preference`, readiness/status fields).
- [x] Binding lifecycle enum + versioning baseline with supersession tracking.
- [x] Binding-to-secret linking and validation at upsert.
- [x] Encrypted DB secret backend (`SecretStoreBackend` default implementation).
- [x] Provider metadata includes regions/required secrets/operations/features/limits.
- [~] Switchover workflow expanded (plan + execute shipped; retirement/deep strategy still pending).

## Phase 3 — Backend Capability-Depth Parity

- [~] Data/schema migration gating by environment stage.
  - [x] `development` auto-applies migration records.
  - [x] `staging`/`production` create pending migrations.
  - [x] Added migration list + apply endpoints.
  - [ ] Add reconciliation status for schema/policy drift.
- [x] Functions idempotency and replay metadata support.
- [~] Events webhook delivery history with attempt/error fields.
  - [x] Delivery records include attempts/timestamps/errors.
  - [ ] Dedicated durable webhook worker + retry queue/backoff.
- [x] Health/usage overview fields expanded with readiness/degradation/switchover/migration context.
- [x] Resolver forwards region + resolved secret material into provider context.

## Phase 4 — Web Admin Control Plane

- [x] PostBase area added to admin shell.
- [x] Dedicated web types + hooks for PostBase read surfaces.
- [ ] Mutating PostBase operator forms/pages (bindings, secrets, switchovers, migration apply).
- [ ] Inline operator remediation UX for readiness failures.

## Phase 5 — Mobile Companion Status

- [x] Read-only Platform status tab under Settings.
- [x] Mobile DTOs/repository/providers for PostBase overview + health endpoints.
- [x] No secret/binding/migration mutation flows added to mobile.

## Next implementation slice (starting now)

1. [x] Land schema migration apply workflow in control-plane API for staging/production.
2. [x] Add frontend mutation screens for migration apply and switchover execute.
3. [~] Add durable webhook delivery worker abstraction and retry persistence.
