# Environment Configuration

| Profile | Purpose | Defaults |
|---|---|---|
| `local` | Fast feedback for developers | SQLite `app.db`, memory-backed Celery, optional providers disabled |
| `staging` | Full integration verification | Managed DB/Redis, real provider sandboxes |
| `production` | Live workloads | Hardened hosts, managed services, monitoring enabled |

## Key Configuration Areas

- App identity: `PROJECT_NAME`, `APP_ENV`, `APP_INSTANCE_NAME`, `APP_REGION`
- Feature flags: `FEATURE_*`
- Communications: `EMAIL_PROVIDER`, `PUSH_PROVIDER`, `SMS_PROVIDER`, fallbacks
- Analytics: `ANALYTICS_PROVIDER`, provider credentials
- Payments: provider-specific enablement and secrets
- Runtime: database, Redis, Celery, CORS, trusted hosts, cookies, media, frontend URLs
- Operations: logging, suspicious-activity thresholds, rate limits, timeout/retry policy, websocket heartbeat/origin settings

## Database Naming Convention

- The default logical database name is `app`.
- In local SQLite mode, this resolves to:
  - `DATABASE_URL=sqlite+aiosqlite:///./app.db`
  - `SYNC_DATABASE_URL=sqlite:///./app.db`
- In non-debug relational deployments, `POSTGRES_DB=app` is the default unless an environment overrides it explicitly.

## Runtime Override Rules

- The backend starts from environment values first.
- After the database connection is available, the `generalsetting` table can override runtime-safe keys.
- Bootstrap-only keys such as `DATABASE_URL` and `SYNC_DATABASE_URL` are intentionally excluded from runtime DB override.
- Startup-sensitive values may still require an application restart even when a database override exists.

## Startup-Sensitive Groups

These values are the most likely to require process restart even if they are runtime-editable:

- middleware and ingress behavior: trusted hosts, proxy trust, CORS, cookies
- worker bootstrap: Celery eager mode, broker wiring, default queue
- database engine behavior: pool size, overflow, timeout, recycle
- storage and filesystem mounting behavior
- websocket process-level heartbeat and idle handling

## Recommended Mental Model

- Environment/profile selection decides the baseline shape of a deployment.
- Runtime-safe DB overrides fine-tune behavior after the app is running.
- Public system APIs are for client-safe discovery only, not for leaking private operational state.
