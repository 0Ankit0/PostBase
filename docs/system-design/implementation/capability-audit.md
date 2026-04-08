# Capability Audit

_Last updated: 2026-04-08_

This audit evaluates implementation readiness across six capability areas and seven parity criteria:

1. API contract
2. Domain model
3. Persistence
4. Async/worker path
5. Operator UX
6. Observability/audit
7. Integration test coverage

Status legend: **PASS** (evidence exists), **FAIL** (missing or insufficient evidence).

---

## Control-plane

| Criterion | Status | Evidence paths | Test/check command evidence |
|---|---|---|---|
| API contract | PASS | `backend/src/postbase/control_plane/api.py`, `backend/src/postbase/control_plane/schemas.py` | `pytest backend/tests/integration/postbase/test_postbase_flow.py -k control_plane` |
| Domain model | PASS | `backend/src/postbase/domain/models.py`, `backend/src/postbase/control_plane/service.py` | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k project` |
| Persistence | PASS | `backend/src/db/session.py`, `backend/alembic/versions/6c2aec86ee51_init.py` | `alembic -c backend/alembic.ini current` |
| Async/worker path | FAIL | (no dedicated control-plane worker/job module under `backend/src/postbase/control_plane/`) | `pytest backend/tests/integration/postbase/test_postbase_flow.py -k job` (expected gap) |
| Operator UX | PASS | `frontend/src/app/(admin-dashboard)/admin/postbase/page.tsx`, `frontend/src/app/(admin-dashboard)/admin/postbase/[projectId]/page.tsx` | `cd frontend && npm run lint` |
| Observability/audit | PASS | `backend/src/postbase/platform/audit.py`, `backend/src/apps/observability/service.py` | `pytest backend/tests/integration/api/test_observability.py` |
| Integration test coverage | PASS | `backend/tests/integration/postbase/test_postbase_flow.py`, `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | `pytest backend/tests/integration/postbase` |

**Remediation ticket (failed criterion):**
- **ID:** CAP-AUD-001
- **Title:** Add async reconciliation worker path for control-plane lifecycle operations
- **Owner:** Platform Backend (Control Plane)
- **Due sprint:** Sprint 2026.09

---

## Auth

| Criterion | Status | Evidence paths | Test/check command evidence |
|---|---|---|---|
| API contract | PASS | `backend/src/postbase/capabilities/auth/api.py`, `backend/src/postbase/capabilities/auth/contracts.py`, `backend/src/apps/iam/api/v1/auth/login.py` | `pytest backend/tests/integration/auth/test_auth_flow.py` |
| Domain model | PASS | `backend/src/apps/iam/models/user.py`, `backend/src/apps/iam/models/role.py` | `pytest backend/tests/unit/iam/models/test_models.py` |
| Persistence | PASS | `backend/alembic/versions/eec72f00ab92_add_social_login_fields.py`, `backend/alembic/versions/e1ecd002528b_add_token_tracking_and_ip_access_.py` | `alembic -c backend/alembic.ini history` |
| Async/worker path | PASS | `backend/src/apps/iam/tasks.py`, `backend/src/apps/core/celery_app.py` | `pytest backend/tests/integration/auth/test_security.py -k ip` |
| Operator UX | PASS | `frontend/src/components/auth/login-form.tsx`, `frontend/src/components/auth/signup-form.tsx`, `frontend/src/app/(auth)/login/page.tsx` | `cd frontend && npm run test -- login` |
| Observability/audit | PASS | `backend/src/apps/iam/schemas/login_attempt.py`, `backend/src/apps/observability/models.py` | `pytest backend/tests/integration/auth/test_security.py` |
| Integration test coverage | PASS | `backend/tests/integration/auth/test_auth_flow.py`, `backend/tests/integration/auth/test_user_flow.py`, `backend/tests/integration/auth/test_tokens.py` | `pytest backend/tests/integration/auth` |

---

## Data

| Criterion | Status | Evidence paths | Test/check command evidence |
|---|---|---|---|
| API contract | PASS | `backend/src/postbase/capabilities/data/api.py`, `backend/src/postbase/capabilities/data/contracts.py` | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k data` |
| Domain model | PASS | `backend/src/postbase/domain/models.py`, `backend/src/postbase/capabilities/data/service.py` | `pytest backend/tests/unit/postbase/test_secret_store.py` |
| Persistence | PASS | `backend/src/postbase/providers/data/postgres_native.py`, `backend/src/db/session.py` | `pytest backend/tests/integration/api/test_general.py` |
| Async/worker path | FAIL | (no dedicated async ingestion/compaction worker in `backend/src/postbase/capabilities/data/`) | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k async` (expected gap) |
| Operator UX | FAIL | (no explicit data capability operator surface under `frontend/src/app/(admin-dashboard)/admin/postbase/`) | `cd frontend && npm run lint` (no dedicated data admin workflow assertion) |
| Observability/audit | PASS | `backend/src/apps/observability/api.py`, `backend/src/postbase/platform/audit.py` | `pytest backend/tests/integration/api/test_observability.py` |
| Integration test coverage | PASS | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k data` |

**Remediation tickets (failed criteria):**
- **ID:** CAP-AUD-002
- **Title:** Implement data async worker pipeline for long-running data operations
- **Owner:** Data Platform Backend
- **Due sprint:** Sprint 2026.10

- **ID:** CAP-AUD-003
- **Title:** Add operator UX for data capability management in admin console
- **Owner:** Frontend Platform + Product Ops
- **Due sprint:** Sprint 2026.10

---

## Storage

| Criterion | Status | Evidence paths | Test/check command evidence |
|---|---|---|---|
| API contract | PASS | `backend/src/postbase/capabilities/storage/api.py`, `backend/src/postbase/capabilities/storage/contracts.py` | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k storage` |
| Domain model | PASS | `backend/src/postbase/domain/models.py`, `backend/src/postbase/capabilities/storage/service.py` | `pytest backend/tests/unit/core/test_storage.py` |
| Persistence | PASS | `backend/src/postbase/providers/storage/local_disk.py`, `backend/src/postbase/providers/storage/s3_compatible.py` | `pytest backend/tests/unit/core/test_storage.py -k s3` |
| Async/worker path | FAIL | (no explicit background object lifecycle worker under `backend/src/postbase/capabilities/storage/`) | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k worker` (expected gap) |
| Operator UX | PASS | `frontend/src/app/(user-dashboard)/settings/page.tsx`, `frontend/src/components/ui/confirm-dialog.tsx` | `cd frontend && npm run lint` |
| Observability/audit | FAIL | (no storage-specific audit trail module/tests identified) | `pytest backend/tests/integration/api/test_observability.py -k storage` (expected gap) |
| Integration test coverage | PASS | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py` | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k storage` |

**Remediation tickets (failed criteria):**
- **ID:** CAP-AUD-004
- **Title:** Add async storage worker path for lifecycle operations (retention, replication, cleanup)
- **Owner:** Storage Backend
- **Due sprint:** Sprint 2026.10

- **ID:** CAP-AUD-005
- **Title:** Add storage-specific audit + observability events and integration checks
- **Owner:** SRE + Storage Backend
- **Due sprint:** Sprint 2026.11

---

## Functions/Jobs

| Criterion | Status | Evidence paths | Test/check command evidence |
|---|---|---|---|
| API contract | PASS | `backend/src/postbase/capabilities/functions/api.py`, `backend/src/postbase/capabilities/functions/contracts.py` | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k function` |
| Domain model | PASS | `backend/src/postbase/domain/models.py`, `backend/src/postbase/capabilities/functions/service.py` | `pytest backend/tests/integration/postbase/test_postbase_flow.py -k function` |
| Persistence | PASS | `backend/src/postbase/providers/functions/celery_runtime.py`, `backend/src/apps/core/celery_app.py` | `pytest backend/test_celery_setup.py` |
| Async/worker path | PASS | `backend/src/postbase/tasks.py`, `backend/src/apps/core/tasks.py`, `backend/src/apps/notification/tasks.py` | `pytest backend/test_celery_setup.py` |
| Operator UX | FAIL | (no dedicated functions/jobs operator interface in `frontend/src/app/(admin-dashboard)/admin/postbase/`) | `cd frontend && npm run lint` (no dedicated jobs UI assertion) |
| Observability/audit | PASS | `backend/src/apps/observability/service.py`, `backend/src/postbase/platform/audit.py` | `pytest backend/tests/integration/api/test_observability.py` |
| Integration test coverage | PASS | `backend/tests/integration/postbase/test_postbase_extended_capabilities.py`, `backend/tests/integration/postbase/test_postbase_flow.py` | `pytest backend/tests/integration/postbase -k function` |

**Remediation ticket (failed criterion):**
- **ID:** CAP-AUD-006
- **Title:** Add operator jobs dashboard (queue depth, retries, dead-letter visibility)
- **Owner:** Frontend Platform + Runtime Team
- **Due sprint:** Sprint 2026.11

---

## Events/Realtime

| Criterion | Status | Evidence paths | Test/check command evidence |
|---|---|---|---|
| API contract | PASS | `backend/src/postbase/capabilities/events/api.py`, `backend/src/postbase/capabilities/events/contracts.py`, `backend/src/apps/websocket/api/v1/ws.py` | `pytest backend/tests/unit/websocket/test_websocket.py` |
| Domain model | PASS | `backend/src/postbase/capabilities/events/service.py`, `backend/src/apps/websocket/schemas/messages.py` | `pytest backend/tests/unit/websocket/test_websocket.py` |
| Persistence | FAIL | (no durable event store model/migration identified for capability event history) | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k event` (expected gap) |
| Async/worker path | PASS | `backend/src/postbase/capabilities/events/webhook_jobs.py`, `backend/src/postbase/capabilities/events/webhook_delivery.py`, `backend/src/postbase/providers/events/redis_pubsub.py` | `pytest backend/tests/integration/postbase/test_postbase_extended_capabilities.py -k webhook` |
| Operator UX | PASS | `frontend/src/hooks/use-websocket.ts`, `frontend/src/types/websocket.ts`, `frontend/src/components/notifications/notification-bell.tsx` | `cd frontend && npm run test -- websocket` |
| Observability/audit | PASS | `backend/src/apps/observability/service.py`, `backend/src/postbase/capabilities/events/service.py` | `pytest backend/tests/integration/api/test_observability.py` |
| Integration test coverage | FAIL | (no dedicated integration suite under `backend/tests/integration` for realtime websocket/event delivery end-to-end) | `pytest backend/tests/integration -k websocket` (expected gap) |

**Remediation tickets (failed criteria):**
- **ID:** CAP-AUD-007
- **Title:** Implement durable event persistence model for replay/audit support
- **Owner:** Realtime Backend
- **Due sprint:** Sprint 2026.10

- **ID:** CAP-AUD-008
- **Title:** Add end-to-end integration test suite for websocket + webhook event delivery
- **Owner:** QA Automation + Realtime Backend
- **Due sprint:** Sprint 2026.11

---

## Remediation and parity-matrix update gate

Per request, `docs/system-design/parity-matrix.md` **is not updated in this change**. Update that matrix only after remediation tickets above are implemented and merged.
