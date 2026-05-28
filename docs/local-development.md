# Local Development

PostBase is **Postgres-only** for backend runtime, migrations, and backend tests. SQLite is not a supported path in this repository.

## Prerequisites

- Python 3.14 with `uv`
- Node.js 20 with `npm`
- Podman with `podman compose`
- Flutter (optional, only for the mobile app)

## Bootstrap profiles

From the repository root:

```bash
make bootstrap-local
```

This command:

1. Creates missing env files from the local templates.
2. Installs backend, frontend, and optional mobile dependencies.
3. Starts Postgres and Redis with `podman compose`.
4. Creates and migrates the local Postgres database `template_local`.

For the staging-like profile:

```bash
make bootstrap-staging
```

If `backend/.env`, `frontend/.env.local`, or `mobile/.env` already exist, bootstrap keeps them. Delete the active env file first if you want to regenerate it from the other profile template.

## Running services

```bash
make backend-dev
make frontend-dev
make mobile-dev
```

Useful infrastructure commands:

```bash
make infra-up
make infra-down
make dev-up
make dev-down
```

## Validation commands

| Area | Full command | Single test / targeted command |
|---|---|---|
| Docs | `make docs` | `python3 scripts/validate_documentation.py` |
| Deploy readiness | `make deploy-readiness` | `python3 scripts/check_deploy_readiness.py` |
| Backend lint | `cd backend && uv run ruff check src tests` | `cd backend && uv run ruff check src/apps/core/config.py` |
| Backend tests | `cd backend && uv run --group test pytest` | `cd backend && uv run --group test pytest tests/unit/core/test_config.py::TestSettings::test_database_urls_are_postgres -q` |
| Frontend lint | `cd frontend && npm run lint` | `cd frontend && npx eslint src/hooks/use-postbase.ts` |
| Frontend typecheck | `cd frontend && npm run typecheck` | `cd frontend && npx tsc --noEmit --pretty false` |
| Frontend tests | `cd frontend && npm run test` | `cd frontend && npx vitest run src/hooks/use-postbase.test.ts` |
| Frontend build | `cd frontend && npm run build` | `cd frontend && NEXT_TELEMETRY_DISABLED=1 npm run build` |
| Mobile lint | `cd mobile && flutter analyze` | `cd mobile && flutter analyze lib/core/router/app_router.dart` |
| Mobile tests | `cd mobile && flutter test` | `cd mobile && flutter test test/postbase_status_model_test.dart` |

Repo-level shortcuts:

```bash
make baseline-checks
make ci
```

## Backend test requirements

Backend tests expect PostgreSQL on the port defined by `DATABASE_URL` and default to the repo's local Podman mapping on `localhost:15432`. The test harness creates and resets the `postbase_test` database automatically, but it does **not** start Postgres for you.

Use either of these before backend tests:

```bash
make bootstrap-local
```

or:

```bash
podman compose up -d db redis
```
