# PostBase Documentation Index

This `docs/` directory is the source of truth for PostBase documentation. The canonical product and architecture specification lives under `docs/system-design`.

## Documentation Map

- `system-design/README.md` — entry point for product scope, architecture, and execution guidance.
- `system-design/requirements/` — capability requirements and user stories.
- `system-design/analysis/` — use cases, business rules, and domain analysis artifacts.
- `system-design/high-level-design/` — architecture, context, and sequence-level diagrams.
- `system-design/detailed-design/` — API, schema, and component-level implementation design.
- `system-design/infrastructure/` — deployment, network, and cloud architecture.
- `system-design/edge-cases/` — behavior for hard scenarios and operational edge conditions.
- `system-design/implementation/` — coding and rollout playbook guidance.
- `system-design/parity-matrix.md` — requirement and API parity tracking against the current codebase.
- `system-design/implementation/parity-implementation-checklist.md` — actionable phase checklist used to drive implementation slices.
- `system-design/implementation/release-gate-checklist.md` — release gate requirements, sign-off owners, and branch protection expectations.

## Validation

Run the docs validation suite from repo root:

```bash
make docs
```

Validation currently checks:

- Canonical structure and required files in `docs/system-design`.
- Mermaid coverage for required diagram documents.
- Required section headings in key docs.
- Presence and format of parity status markers in `system-design/parity-matrix.md`.

## Status Legend

Use these status markers consistently in parity tracking:

- `implemented` — delivered in code and backed by tests.
- `partial` — present but missing documented depth or workflow completeness.
- `planned` — documented intent not yet implemented in code.
