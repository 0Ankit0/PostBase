# PostBase Requirement and API Parity Matrix

## Status

- `implemented`: Delivered in code and validated by tests/checks.
- `partial`: Partially delivered; workflow depth, durability, or operator UX is still incomplete.
- `planned`: Documented in system design but not yet implemented.

## Capability and Workflow Parity

| Area | Requirement / Workflow | Status | Code Reference(s) | Test / Check Reference(s) | Gap Notes |
|---|---|---|---|---|---|
| Docs/tooling | Canonical docs index, README links, and docs validation | implemented | `docs/README.md`, `README.md`, `scripts/validate_documentation.py` | `make docs` | Docs pipeline now validates canonical `docs/system-design`. |
| Release operations | Deploy-readiness automation gate (`make deploy-readiness`) | implemented | `scripts/check_deploy_readiness.py`, `Makefile` | `make deploy-readiness` | Release blockers are validated automatically before CI/local release runs. |
| Control plane | Project lifecycle APIs | implemented | `backend/src/postbase/control_plane/api.py`, `backend/src/postbase/control_plane/service.py` | `backend/tests/integration/postbase/test_postbase_flow.py` | Baseline create/list and project access flow are in place. |
| Control plane | Environment lifecycle + operational metadata (`region_preference`, readiness/status) | implemented | `backend/src/postbase/domain/models.py`, `backend/src/postbase/control_plane/schemas.py` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Metadata fields are persisted and returned. |
| Bindings | Versioned lifecycle states (`pending_validation`, `active`, `deprecated`, `retired`, `failed`, `disabled`) | implemented | `backend/src/postbase/domain/enums.py`, `backend/src/postbase/domain/models.py`, `backend/src/postbase/control_plane/service.py` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Lifecycle transitions now include explicit operator controls for supersession, disablement, and retirement sequencing. |
| Bindings | Binding-to-secret references + validation before activation | implemented | `backend/src/postbase/domain/models.py`, `backend/src/postbase/control_plane/service.py`, `backend/src/postbase/control_plane/schemas.py` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Bindings validate required secret kinds and region support before active promotion. |
| Secrets | Encrypted secret backend + masked secret APIs | implemented | `backend/src/postbase/platform/secret_store.py`, `backend/src/postbase/control_plane/service.py`, `backend/src/apps/core/config.py` | `backend/tests/unit/postbase/test_secret_store.py` | Encrypted DB storage is in place behind `DbEncryptedSecretStore`. |
| Provider catalog | Metadata normalization (`supported_regions`, `required_secret_kinds`, operations, optional features, limits) | implemented | `backend/src/postbase/platform/contracts.py`, `backend/src/postbase/platform/seeding.py` | `backend/tests/integration/postbase/test_postbase_flow.py` | Metadata fields are seeded and consumed by binding validation. |
| Switchovers | Plan + execute APIs with audit trail | implemented | `backend/src/postbase/control_plane/api.py`, `backend/src/postbase/control_plane/service.py`, `backend/src/postbase/platform/audit.py` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Plan + execute workflows are surfaced in API and operator UX with auditable strategy-driven operations. |
| Data/schema | Tracked migrations with stage-gated apply/reconcile | implemented | `backend/src/postbase/domain/models.py`, `backend/src/postbase/capabilities/data/service.py` | `backend/tests/integration/postbase/test_postbase_flow.py` | Stage-aware migration flows include pending/apply controls and reconciliation visibility in operator dashboards. |
| Functions | Invocation idempotency/replay + enriched execution metadata | implemented | `backend/src/postbase/capabilities/functions/api.py`, `backend/src/postbase/capabilities/functions/contracts.py`, `backend/src/postbase/providers/functions/` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Idempotency replay metadata and timestamps are returned. |
| Events | Subscription target constraint (`room | webhook`) and delivery history fields | implemented | `backend/src/postbase/capabilities/events/contracts.py`, `backend/src/postbase/providers/events/` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Target type is constrained and delivery attempts/timestamps/errors are captured. |
| Events | Webhook worker with durable retries/backoff queue | implemented | `backend/src/postbase/providers/events/redis_pubsub.py`, `backend/src/postbase/providers/events/websocket_gateway.py`, `backend/src/postbase/tasks.py` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Webhook deliveries are queued durably with persisted retry attempts and backoff-based reprocessing. |
| Health & usage | Project/environment overview with readiness/degradation/switchover/migration visibility | implemented | `backend/src/postbase/control_plane/schemas.py`, `backend/src/postbase/control_plane/service.py` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Overview now includes readiness and migration/switchover indicators. |
| Provider execution | Resolver passes region + resolved secret material to providers | implemented | `backend/src/postbase/platform/contracts.py`, `backend/src/postbase/platform/resolver.py` | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | Resolved binding contract now includes decrypted secret map + region. |
| Web admin | PostBase admin area/types/hooks/pages | implemented | `frontend/src/app/(admin-dashboard)/admin/postbase/`, `frontend/src/hooks/use-postbase.ts`, `frontend/src/types/postbase.ts` | `cd frontend && npm run typecheck`, `cd frontend && npm run lint` | Read and mutation workflows (bindings, secrets, migration apply, and switchovers) are available in admin UX. |
| Mobile companion | Read-only PostBase `Platform` status under Settings | implemented | `mobile/lib/features/settings/presentation/pages/settings_page.dart`, `mobile/lib/core/repositories/postbase_repository.dart`, `mobile/lib/core/providers/postbase_provider.dart` | `mobile/test/postbase_status_model_test.dart` | Read-only status surface is implemented with overview + health fetching. |
| Operations | Automated remediation playbooks for readiness failures | implemented | `frontend/src/app/(admin-dashboard)/admin/postbase/[projectId]/page.tsx` | `cd frontend && npm run typecheck` | Inline remediation controls and run-now execution checklist are available in admin UX. |
| Operations | Autonomous policy drift auto-heal orchestration | implemented | `docs/system-design/edge-cases/operations.md` | `make docs` | Scheduled drain automation and operator-triggered drain controls are implemented. |

## Advertised API Shape Parity

| API / Type | Status | Current Implementation | Remaining Gap |
|---|---|---|---|
| `EnvironmentRead.region_preference` | implemented | Present in schema/model/API | None. |
| `EnvironmentRead.status` | implemented | Present in schema/model/API | None. |
| `EnvironmentRead.readiness_state` + `readiness_detail` | implemented | Present in schema/model/API | None. |
| `EnvironmentRead.last_validated_at` | implemented | Present in schema/model/API | None. |
| `BindingCreate.secret_ref_ids` | implemented | Present and used in binding validation flow | None. |
| `BindingCreate.region` | implemented | Present and validated against provider metadata | None. |
| `BindingRead` lifecycle/diagnostics/secret links/supersession | implemented | Present in schema/API responses | None. |
| `POST /switchovers/{switchover_id}/execute` | implemented | Route available | None. |
| `GET /bindings/{binding_id}/switchovers` | implemented | Route available | None. |
| `GET /switchovers/{switchover_id}` | implemented | Route available | None. |
| Resolved binding includes region + resolved secrets | implemented | Present in `ResolvedBinding` and resolver output | None. |
| `ExecutionRead` idempotency/retry/timestamps/log | implemented | Present in contracts/providers | None. |
| `SubscriptionCreateRequest.target_type = room\|webhook` | implemented | Literal type constrained in contracts | None. |
| `DeliveryRead.attempt_count/delivered_at/error_text` | implemented | Present in contracts/providers/domain model with durable worker retry persistence | None. |

## Phase-Level Cross-Check Summary

| Phase | Status | Cross-check note |
|---|---|---|
| Phase 1: Docs + validation baseline | implemented | Canonical docs tree, README links, validator, and parity matrix are present. |
| Phase 2: Backend control-plane foundation | implemented | Core metadata/lifecycle/secret/switchover workflows are implemented with operator controls. |
| Phase 3: Backend capability-depth parity | implemented | Functions/events/overview parity landed with migration reconciliation and durable webhook retries. |
| Phase 4: Web admin control plane | implemented | PostBase area includes mutation workflows for secrets, bindings, migration apply, and switchovers. |
| Phase 5: Mobile companion status | implemented | Read-only Platform status surface added under Settings; no mutation flows introduced. |


## Status Marker Reference

| Marker | Example usage |
|---|---|
| implemented | Delivered and validated in this repository. |
| partial | Reserved for future in-progress slices when only part of a workflow ships. |
| planned | Reserved for documented intent before implementation starts. |
