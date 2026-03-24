# Use Case Descriptions - Backend as a Service Platform

## UC-01: Create Project and Environment
**Primary Actor**: Project Owner / Tenant Admin  
**Goal**: Provision a workspace where capabilities can be configured consistently.

**Preconditions**:
- Tenant exists and owner has project-creation rights.
- Platform capacity and adapter catalog are available.

**Main Flow**:
1. Owner creates a project and chooses one or more environments.
2. System generates project metadata, environment records, and default capability states.
3. Owner configures access roles and baseline policies.
4. Control plane reports environment readiness.

---

## UC-02: Bind Providers for Capabilities
**Primary Actor**: Project Owner / Tenant Admin

**Main Flow**:
1. Owner opens the capability catalog.
2. Owner selects supported providers for storage, functions, or realtime.
3. System validates compatibility, secrets, and required configuration.
4. Binding becomes active after readiness checks succeed.

**Exceptions**:
- E1: Adapter not certified for capability profile -> binding is blocked.
- E2: Required secret missing -> activation remains pending.

---

## UC-03: Use Auth Facade from Application Code
**Primary Actor**: App Developer

**Main Flow**:
1. Developer integrates the platform SDK.
2. App invokes auth methods for signup, session creation, token validation, or recovery.
3. Platform facade resolves to the active auth implementation and project policy.
4. Unified auth responses are returned to the app.

---

## UC-04: Manage Schema and Use Data API
**Primary Actor**: App Developer

**Main Flow**:
1. Developer defines or updates schema through the control plane or migration API.
2. System validates schema changes against environment rules.
3. Postgres schema and metadata are updated.
4. Application uses the unified data API for CRUD and filtered access.

---

## UC-05: Upload File Through Storage Facade
**Primary Actor**: App Developer or Application End User (through app)

**Main Flow**:
1. App requests upload intent or signed upload flow.
2. System resolves the active storage provider binding.
3. File upload and metadata registration complete through the adapter.
4. Unified file response is returned through the facade.

---

## UC-06: Deploy and Run Function or Job
**Primary Actor**: App Developer

**Main Flow**:
1. Developer deploys code or job configuration through the functions facade.
2. Platform validates runtime profile, secrets, and execution policy.
3. Adapter-backed execution environment receives the deployment.
4. Invocations, schedules, and execution records are exposed uniformly.

---

## UC-07: Subscribe to Realtime or Event Stream
**Primary Actor**: App Developer

**Main Flow**:
1. Developer registers channels, subscriptions, or event handlers.
2. Platform validates scope and capability availability.
3. Active adapter publishes or fans out events using provider-specific mechanisms.
4. Consumers receive events through a stable facade contract.

---

## UC-08: Switch Provider with Migration Workflow
**Primary Actor**: Project Owner / Tenant Admin or Platform Operator

**Main Flow**:
1. User selects a new provider for a capability.
2. System evaluates compatibility and produces a migration plan.
3. Migration steps run according to capability-specific switchover strategy.
4. New provider binding becomes active and old binding is deprecated or retired.

**Exceptions**:
- E1: Migration validation fails -> switchover is blocked before activation.
- E2: Provider health degrades during cutover -> rollback or pause state is entered.
