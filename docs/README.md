# FastAPI Template Documentation

This documentation set turns the repository into a reusable product template with configurable modules, pluggable providers, and deployment-ready operating guidance.

## Documentation Structure

- `requirements/` defines scope, personas, and success criteria.
- `analysis/` captures domain rules, workflows, actors, and events.
- `high-level-design/` explains the architecture and major runtime flows.
- `detailed-design/` drills into API contracts, components, and data models.
- `infrastructure/` describes environments, networking, deployment, and CI/CD.
- `edge-cases/` records template-specific failure modes and operational concerns.
- `implementation/` gives build, rollout, and testing playbooks.
- `onboarding/` helps teams bootstrap a fresh project from the template.
- `onboarding/project-orientation.md` explains how the whole project fits together before you start changing it.
- `implementation/working-principles.md` explains the design rules the template follows.
- `onboarding/configuration-management.md` explains how configuration moves through backend, web, and mobile.
- `onboarding/modifying-the-template.md` gives a safe process for future modifications.
- `onboarding/template-finalization-checklist.md` gives the handoff checklist for turning the starter into a real product.
- `infrastructure/production-hardening-checklist.md` lists the deployment reviews that still belong to each downstream project.

## Key Features

- Feature-flagged modules for auth, multi-tenancy, notifications, analytics, finance, and websockets.
- Provider-driven outbound communications for email, push, SMS, analytics, and payments.
- Domain-aware Casbin RBAC with SQL-managed roles and permissions mirrored into runtime policy tuples.
- Multi-device notification registry across Web Push, FCM, and OneSignal.
- Database-backed general settings with environment fallback and migration seeding.
- Shared backend, web, and mobile runtime capability discovery, including public general settings.
- Centralized operational configuration for logging, observability, rate limits, storage, Celery, cookies, hosts, and websocket behavior.
- CI, environment, and release documentation for reuse across future projects.

## Getting Started

1. Read [requirements/requirements.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/requirements/requirements.md).
2. Read [onboarding/project-orientation.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/onboarding/project-orientation.md).
3. Follow [onboarding/local-setup.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/onboarding/local-setup.md).
4. Understand config flow with [onboarding/configuration-management.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/onboarding/configuration-management.md).
5. Follow [onboarding/template-finalization-checklist.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/onboarding/template-finalization-checklist.md) before you start deleting or renaming template features.
6. Configure providers using [onboarding/provider-configuration.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/onboarding/provider-configuration.md).
7. Choose enabled modules and environment profile from [infrastructure/environment-configuration.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/infrastructure/environment-configuration.md).
8. Understand authorization flow with [implementation/casbin-rbac.md](/Users/ankit/Projects/Python/fastapi/fastapi_template/docs/implementation/casbin-rbac.md).
9. Validate docs with `python3 scripts/validate_documentation.py`.

## Documentation Status

- Phase coverage: requirements, analysis, design, infrastructure, edge cases, implementation, onboarding.
- Diagram coverage: Mermaid-based system, process, architecture, and deployment views.
- Validation coverage: enforced by `scripts/validate_documentation.py`.
- Current status: template docs aligned with the Project-Ideas structure and extended for provider-driven runtime configuration, database-backed settings overrides, and operational configuration guidance.
