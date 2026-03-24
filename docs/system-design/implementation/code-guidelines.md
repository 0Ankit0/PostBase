# Code Guidelines - Backend as a Service Platform

## 1. Recommended Module Boundaries
- `apps/control-plane`: operator and tenant admin UI
- `apps/api`: public API and SDK-facing endpoints
- `apps/realtime-gateway`: subscriptions and event transport
- `workers/orchestrator`: switchover, provisioning, and async capability tasks
- `packages/domain`: shared domain models and policies
- `packages/capabilities`: auth, data, storage, functions, events facade contracts
- `packages/providers`: adapter implementations and conformance test kits
- `packages/platform`: secrets, auditing, usage, config, and shared utilities

## 2. Coding Standards
- Keep facade contracts provider-agnostic; provider-specific details belong only in adapters.
- Model every capability with a contract interface, capability profile, and conformance tests.
- Treat PostgreSQL schema changes and metadata writes as audited domain events.
- Use idempotency for provisioning, migrations, deployments, and event-producing operations.
- Prefer explicit failure states over silent fallback to alternate providers.

## 3. Adapter Design Rules
- Each adapter must declare supported operations, limits, optional features, and compliance attributes.
- Adapters must map provider errors into the shared platform error taxonomy.
- Adapters must expose health probes, readiness checks, and structured execution traces.
- Provider migration helpers must be separate from steady-state runtime handlers when capabilities differ significantly.

## 4. Testing Expectations
- Unit tests for policy, compatibility, and migration planning logic.
- Contract tests for every capability facade against all certified adapters.
- Integration tests for project provisioning, binding activation, and provider switchover.
- Load tests for data API, event fanout, and worker orchestration.
- Recovery tests for queue replay, Postgres failover, and secret rotation.
