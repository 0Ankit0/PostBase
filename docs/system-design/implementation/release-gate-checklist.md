# Release Gate Checklist

Use this checklist before creating a release tag from a `release/*` branch.

## Required CI Gates

| Gate | Command | Required check name | Owner |
| --- | --- | --- | --- |
| Documentation validation | `make docs` | `docs` | Frontend lead |
| Deploy readiness validation | `make deploy-readiness` | `deploy-readiness` | SRE |
| Backend lint | `cd backend && uv run ruff check src tests` | `backend-lint` | Backend lead |
| Backend unit/API tests | `cd backend && uv run pytest tests/unit tests/integration/api` | `backend-tests` | Backend lead |
| Backend integration suite | `cd backend && uv run pytest tests/integration/postbase tests/integration/auth` | `backend-integration` | Backend lead |
| Frontend lint | `cd frontend && npm run lint` | `frontend-lint` | Frontend lead |
| Frontend typecheck | `cd frontend && npm run typecheck` | `frontend-typecheck` | Frontend lead |
| Frontend tests/build | `cd frontend && npm run test && npm run build` | `frontend-tests` | Frontend lead |
| Mobile lint (analyze) | `cd mobile && flutter analyze` | `mobile-lint` | Mobile lead |
| Mobile tests | `cd mobile && flutter test` | `mobile-tests` | Mobile lead |

## Required Human Sign-Offs (pre-tag)

All sign-offs are mandatory before tagging a release.

- [ ] Backend lead sign-off (backend architecture, migrations, API compatibility)
- [ ] Frontend lead sign-off (UI/API contract compatibility, release notes accuracy)
- [ ] SRE sign-off (operational readiness, observability, rollback readiness)
- [ ] Security sign-off (vulnerability review, secrets handling, audit coverage)

## Failure Triage Labels

Use the following labels when a required gate fails:

- `triage:flaky-infrastructure` for nondeterministic failures or CI environment/platform outages.
- `triage:code-regression` for deterministic test/lint/type regressions introduced by code changes.

## Branch Protection Requirement

`master`, `main`, `develop`, and `release/**` branch protection must require all implementation gates to be green before merge: `docs`, `deploy-readiness`, `backend-lint`, `backend-tests`, `backend-integration`, `frontend-lint`, `frontend-typecheck`, `frontend-tests`, `mobile-lint`, and `mobile-tests`.

## Release Tagging Rule

Do not create or move a release tag until:

1. All required CI gates listed above are green in CI.
2. Backend lead, frontend lead, SRE, and security sign-offs are all recorded in the release PR.
