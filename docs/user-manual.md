# PostBase User Manual

This guide walks through a complete local PostBase flow: start the stack, create an operator account, create a tenant/project/environment, issue an environment API key, then use the PostBase auth and data APIs.

The examples below use:

```bash
export API=http://localhost:8000/api/v1
export WEB=http://localhost:3000
```

## 1. Start the project

From the repository root:

```bash
make bootstrap-local
make backend-dev
make frontend-dev
```

Optional:

```bash
make mobile-dev
```

Verify the backend is running:

```bash
curl "$API/system/health/"
```

Expected response:

```json
{"status":"ok","service":"PostBase"}
```

## 2. Create an operator account

Use the platform auth API and ask for tokens in the response body:

```bash
SIGNUP_RESPONSE=$(curl -sS -X POST "$API/auth/signup/?set_cookie=false" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "platform_owner",
    "email": "owner@example.com",
    "password": "OwnerPass123!",
    "confirm_password": "OwnerPass123!"
  }')

export OPERATOR_TOKEN=$(printf '%s' "$SIGNUP_RESPONSE" | jq -r '.access')
```

You can now call operator APIs with:

```bash
export OPERATOR_AUTH="Authorization: Bearer $OPERATOR_TOKEN"
```

## 3. Create a tenant

```bash
TENANT_RESPONSE=$(curl -sS -X POST "$API/tenants/" \
  -H "$OPERATOR_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme",
    "slug": "acme",
    "description": "Acme tenant"
  }')

export TENANT_ID=$(printf '%s' "$TENANT_RESPONSE" | jq -r '.id')
```

What this does:

1. Creates the top-level tenant/workspace.
2. Makes the calling user the owner.
3. Unlocks control-plane actions for projects and environments in that tenant.

## 4. Create a project and environment

Create a project:

```bash
PROJECT_RESPONSE=$(curl -sS -X POST "$API/projects" \
  -H "$OPERATOR_AUTH" \
  -H "Content-Type: application/json" \
  -d "{
    \"tenant_id\": \"$TENANT_ID\",
    \"name\": \"Main Project\",
    \"slug\": \"main_project\",
    \"description\": \"Primary project\"
  }")

export PROJECT_ID=$(printf '%s' "$PROJECT_RESPONSE" | jq -r '.id')
```

Create a development environment:

```bash
ENV_RESPONSE=$(curl -sS -X POST "$API/projects/$PROJECT_ID/environments" \
  -H "$OPERATOR_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Development",
    "slug": "dev",
    "stage": "development"
  }')

export ENV_ID=$(printf '%s' "$ENV_RESPONSE" | jq -r '.id')
```

## 5. Issue an environment API key

Create an anon key for end-user auth and data access:

```bash
KEY_RESPONSE=$(curl -sS -X POST "$API/environments/$ENV_ID/keys" \
  -H "$OPERATOR_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "client_anon",
    "role": "anon"
  }')

export POSTBASE_KEY=$(printf '%s' "$KEY_RESPONSE" | jq -r '.plaintext_key')
```

Use this header for PostBase capability APIs:

```bash
export POSTBASE_KEY_HEADER="X-PostBase-Key: $POSTBASE_KEY"
```

## 6. Create a namespace and table

Create a namespace:

```bash
NAMESPACE_RESPONSE=$(curl -sS -X POST "$API/environments/$ENV_ID/data/namespaces" \
  -H "$OPERATOR_AUTH" \
  -H "Content-Type: application/json" \
  -d '{"name": "app"}')

export NAMESPACE_ID=$(printf '%s' "$NAMESPACE_RESPONSE" | jq -r '.id')
```

Create an owner-scoped table:

```bash
curl -sS -X POST "$API/environments/$ENV_ID/data/namespaces/$NAMESPACE_ID/tables" \
  -H "$OPERATOR_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "posts",
    "columns": [
      {"name": "title", "type": "string", "nullable": false},
      {"name": "auth_user_id", "type": "integer", "nullable": false}
    ],
    "policy_mode": "owner",
    "owner_column": "auth_user_id"
  }'
```

This table lets authenticated PostBase users see only their own rows.

For advanced Postgres provisioning, you can add `advanced_features` to the same table creation payload. This keeps Postgres-specific behavior attached to the control-plane definition while still exposing the same `/api/v1/data/*` facade for CRUD:

```bash
curl -sS -X POST "$API/environments/$ENV_ID/data/namespaces/$NAMESPACE_ID/tables" \
  -H "$OPERATOR_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "audit_events",
    "columns": [
      {"name": "tenant_id", "type": "integer", "nullable": false},
      {"name": "created_at", "type": "datetime", "nullable": false},
      {"name": "title", "type": "citext", "nullable": false}
    ],
    "policy_mode": "public",
    "advanced_features": {
      "indexes": [
        {
          "name": "ix_audit_tenant_created",
          "columns": ["tenant_id", "created_at"],
          "method": "btree"
        }
      ],
      "partitioning": {
        "strategy": "range",
        "columns": ["created_at"],
        "partitions": [
          {"name": "audit_events_2026_h1", "from_value": "2026-01-01", "to_value": "2026-07-01"},
          {"name": "audit_events_2026_h2", "from_value": "2026-07-01", "to_value": "2027-01-01"}
        ]
      },
      "sharding": {
        "strategy": "logical",
        "shard_key": "tenant_id",
        "shard_count": 8
      },
      "replication": {
        "mode": "logical",
        "publication_name": "audit_events_pub"
      },
      "listen_notify": [
        {
          "channel": "audit_runtime",
          "events": ["insert", "update"],
          "payload_columns": ["tenant_id", "title"]
        }
      ]
    }
  }'
```

The response includes `advanced_features_json.integration_manifest`, which tells you which Postgres features were provisioned directly and which topology-oriented capabilities still require external infrastructure or client routing.

## 7. Sign up an application user in the environment

Now switch from operator APIs to the PostBase capability auth API:

```bash
APP_SIGNUP_RESPONSE=$(curl -sS -X POST "$API/auth/users" \
  -H "$POSTBASE_KEY_HEADER" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "app_user",
    "email": "app@example.com",
    "password": "AppUser123!"
  }')

export APP_ACCESS_TOKEN=$(printf '%s' "$APP_SIGNUP_RESPONSE" | jq -r '.tokens.access_token')
export APP_BEARER="Authorization: Bearer $APP_ACCESS_TOKEN"
```

Check the current environment user:

```bash
curl -sS "$API/auth/me" -H "$APP_BEARER"
```

## 8. Write and read data

Insert a row:

```bash
curl -sS -X POST "$API/data/app/posts" \
  -H "$APP_BEARER" \
  -H "Content-Type: application/json" \
  -d '{
    "values": {
      "title": "hello world"
    }
  }'
```

List rows:

```bash
curl -sS "$API/data/app/posts" -H "$APP_BEARER"
```

Query rows with the canonical query payload:

```bash
curl -sS -X POST "$API/data/query" \
  -H "$APP_BEARER" \
  -H "Content-Type: application/json" \
  -d '{
    "namespace": "app",
    "table": "posts",
    "filters": [
      {"field": "title", "op": "eq", "value": "hello world"}
    ],
    "pagination": {
      "limit": 10,
      "offset": 0
    },
    "sort": [
      {"field": "id", "direction": "asc"}
    ]
  }'
```

## 9. Use the web and mobile clients

### Web app

With backend and frontend running:

1. Open `http://localhost:3000`.
2. Use `/signup` or `/login` for platform auth.
3. Use `/tenants` to manage tenant membership and invitations.
4. Use `/admin/postbase` to inspect PostBase projects, environments, secrets, migrations, and switchovers.
5. Use `/dashboard`, `/settings`, `/notifications`, `/tokens`, and `/profile` for the end-user surface.

### Mobile app

The Flutter app shares the same backend and environment configuration:

1. Start it with `make mobile-dev` or `cd mobile && flutter run`.
2. Sign in with the same backend auth account.
3. Use Home, Notifications, Settings, and Profile in the bottom navigation shell.
4. Open Settings to see the read-only PostBase platform status surface.

## 10. Useful next checks

Open the generated OpenAPI docs:

```bash
open http://localhost:8000/docs
```

List the seeded provider catalog:

```bash
curl -sS "$API/provider-catalog" -H "$OPERATOR_AUTH"
```

That response should include providers such as `local-postgres`, `postgres-native`, `local-disk`, `celery-runtime`, and `redis-pubsub`. For `postgres-native`, the catalog metadata also advertises optional features such as partitioning, replication, sharding, extensions, indexes, and LISTEN/NOTIFY support.
