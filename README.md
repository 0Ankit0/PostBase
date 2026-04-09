# PostBase

PostBase is a backend platform with a control plane for projects, environments, provider bindings, and capability operations across auth, data, storage, functions, and events.

## Quick Start

1. Read the docs index: [`docs/README.md`](docs/README.md).
2. Review the canonical system design: [`docs/system-design/README.md`](docs/system-design/README.md).
3. Bootstrap a fresh local environment (env defaults + dependencies + infra + schema):
   - `make bootstrap-local`
4. Start services as needed:
   - Backend: `make backend-dev`
   - Frontend: `make frontend-dev`
   - Mobile: `make mobile-dev`

## Deterministic Bring-up Profiles

- Local development profile: `make bootstrap-local`
- Staging-like profile (same bootstrap command path, staged runtime defaults): `make bootstrap-staging`

Both profiles provision:

- default runnable env files for backend/frontend/mobile,
- required infrastructure services (Postgres + Redis), and
- initial backend schema state via migrations.

## Baseline checks

After bootstrapping from a clean clone, run all baseline quality checks with:

```bash
make baseline-checks
```

## Documentation

- Canonical architecture and product specification: [`docs/system-design`](docs/system-design).
- Requirement/API parity tracker: [`docs/system-design/parity-matrix.md`](docs/system-design/parity-matrix.md).
- Documentation validation: `make docs`.

## Validation and Testing

- Docs: `make docs`
- Backend lint/tests: `make backend-lint` / `make backend-test`
- Frontend lint/typecheck/tests/build: `make frontend-lint` / `make frontend-test`
- Mobile lint/tests: `make mobile-lint` / `make mobile-test`
- Full local quality bar: `make ci`
