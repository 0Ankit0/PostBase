# Deployment Diagram

```mermaid
flowchart TB
  Web[Next.js Container]
  Mobile[Flutter Release Build]
  API[FastAPI Container]
  Worker[Celery Worker]
  DB[(Postgres / SQLite)]
  Redis[(Redis)]
  Providers[(External Providers)]

  Web --> API
  Mobile --> API
  API --> DB
  API --> Redis
  Worker --> Redis
  API --> Providers
  Worker --> Providers
```
