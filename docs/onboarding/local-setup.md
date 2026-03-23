# Local Setup

The template now has one documented bootstrap path from the repository root. Use it first before you start customizing anything.

## Bootstrap Workflow

1. Run `make setup`.
   This copies env templates if needed, installs backend dependencies with `uv`, installs frontend dependencies with `npm`, and installs Flutter dependencies when Flutter is available.
2. Review the generated env files:
   - `backend/.env`
   - `frontend/.env.local`
   - `mobile/.env`
3. Start infrastructure with `make infra-up`.
4. Run database migrations with `make backend-migrate`.
   This creates the schema and seeds the `generalsetting` table from the current environment baseline.

## Run The Applications

- API: `make backend-dev`
- Web: `make frontend-dev`
- Mobile: `make mobile-dev`

If you prefer containers for everything, `make dev-up` still works, but the root bootstrap path above is the recommended template workflow.

## Validate The Starter

1. Run `make health-check` after the backend is up.
2. Confirm these discovery endpoints respond:
   - `/api/v1/system/health/`
   - `/api/v1/system/ready/`
   - `/api/v1/system/capabilities/`
   - `/api/v1/system/providers/`
   - `/api/v1/system/general-settings/`
3. Run `make ci` before treating the starter as your project baseline.

## Notes About Configuration

- The backend settings model reads process environment and `backend/.env` by default.
- External process env injection is still allowed and overrides file values, but the template’s primary editable file is `backend/.env`.
- For local SQLite development, confirm that the backend is using `app.db` unless you intentionally override the database name.
- Some runtime-editable settings are still startup-sensitive. Middleware, Celery bootstrap, DB engine options, and similar process wiring may require a restart after a DB override.
