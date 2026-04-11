# Template Release Checklist

Use this checklist when you are turning the boilerplate into a real project and want one last pass before treating it as your team’s base.

## Identity And Setup

- Set project identity values in `backend/.env.example` and `backend/.env.staging.example` (for example: `PROJECT_NAME`, `APP_INSTANCE_NAME`).
- Set frontend identity values in `frontend/.env.local.example` and `frontend/.env.staging.local.example` (for example: `NEXT_PUBLIC_APP_NAME`).
- Set mobile identity values in `mobile/.env.example` and `mobile/.env.staging.example` (for example: `PROJECT_NAME`).
- Confirm package/app identifiers in `backend/pyproject.toml`, `frontend/package.json`, and `mobile/pubspec.yaml`.
- Copy local env files from templates with `make copy-env` (creates `.env` variants when they do not already exist).

## Product Shape

- Choose which `FEATURE_*` modules remain enabled.
- Remove routes, pages, and docs for modules your project will never ship.
- Choose your primary providers for email, push, SMS, analytics, maps, and payments.

## Security And Operations

- Move secrets into your deployment secret manager.
- Review trusted hosts, proxy trust, cookies, rate limits, and suspicious-activity thresholds.
- Choose `local` or `s3` storage intentionally and verify media URLs.

## Validation

- Run `make setup`.
- Run `make infra-up`.
- Run `make backend-migrate`.
- Run `make health-check`.
- Run `make docs`.
- Run `make deploy-readiness`.
- Run `make ci`.

## Reading Path

- Read `docs/README.md`.
- Read `docs/system-design/README.md`.
- Read `docs/system-design/implementation/release-gate-checklist.md`.
- Read `docs/system-design/infrastructure/production-readiness-definition-of-done.md`.
