# Deployment

## Runtime Shape

The production runtime is a Docker image run through Docker Compose with three
services:

- `web`: runs Gunicorn and applies startup migrations.
- `scheduler`: runs `python manage.py run_backup_scheduler`.
- `mcp`: runs `python -m invoices_mcp.server` for the authenticated Streamable
  HTTP MCP endpoint with `RUN_MIGRATIONS=0`.

All services use the same image and share the same mounted runtime state:

- `./db:/app/db`
- `./media:/app/media`
- `./.env:/app/.env:ro`

For the SQLite deployment path, the Django containers should resolve the
database to `/app/db/db.sqlite3`. The MCP service does not run migrations and
uses the web/API service through `INVOICES_MCP_API_BASE_URL`.

See [MCP server](mcp-server.md) for MCP environment variables, token setup,
endpoint URL shape, artifact limits, Streamable HTTP client examples, and
operational checks.

## Local Docker Commands

Build a local image:

```bash
docker build -t invoices:local .
```

Run a one-off container:

```bash
mkdir -p db media
docker run --rm -p 8000:8000 --env-file .env -e RUN_MIGRATIONS=1 \
  -v "$(pwd)/db:/app/db" \
  -v "$(pwd)/media:/app/media" \
  -v "$(pwd)/.env:/app/.env:ro" \
  invoices:local
```

Run the Compose stack:

```bash
docker compose up -d
```

Override the image used by Compose:

```bash
INVOICES_IMAGE=git.ultramac.work/lifeisgoodlabs/invoices:some-tag docker compose up -d
```

## Production Rollout

The canonical live deploy command is:

```bash
./scripts/deploy.sh
```

It performs the full rollout:

- resolves deploy-managed runtime values;
- builds and pushes the image through `scripts/build_and_push.sh`;
- exports one `INVOICES_IMAGE` value for all services;
- pulls the new image for `web`, `scheduler`, and `mcp`;
- recreates `web` before `scheduler` and `mcp`;
- runs `scripts/verify_deploy.sh`.

Useful inputs:

- `REGISTRY_HOST`, default `git.ultramac.work`.
- `REGISTRY_IMAGE`, default `git.ultramac.work/lifeisgoodlabs/invoices`.
- `TAG`, default `latest`.
- `COMPOSE_PROJECT_NAME`, default `03-invoices`.
- `PHASE_APP`, default `lifeisgoodlabs-invoices`.
- `PHASE_ENV`, default `Development`.

`SECRET_KEY` and `RENDER_EXTERNAL_HOSTNAME` are required before rollout.
MCP rollout also requires runtime values for `INVOICES_MCP_API_TOKEN` and
`INVOICES_MCP_CLIENT_TOKENS`; deploy does not create or rotate these tokens.
Explicit shell exports and repo-root `.deploy.env` values win first; Phase can
fill missing managed values when the Phase CLI is available and authenticated.

The deploy script writes the managed host values into `.env` while preserving
unrelated entries. Do not manually hotfix `.env` after deployment for values
that should come from the deploy path.

## Verification

Run the tracked verification script:

```bash
./scripts/verify_deploy.sh
```

Equivalent manual checks:

```bash
COMPOSE_PROJECT_NAME=03-invoices docker compose ps web scheduler mcp
curl -H "Host: invoices.ultramac.work" http://127.0.0.1:8000/
COMPOSE_PROJECT_NAME=03-invoices docker compose logs --no-color --tail 50 scheduler
COMPOSE_PROJECT_NAME=03-invoices docker compose exec -T mcp python scripts/mcp_probe.py --url http://127.0.0.1:8765/mcp/ --token "<INVOICES_MCP_CLIENT_TOKEN>"
```

Use the host-header probe when verifying production behavior. It catches host
routing and `ALLOWED_HOSTS` mistakes that localhost-only checks can miss. The
response should be a non-400 application response, typically a redirect to
login.

Scheduler logs should not contain Python tracebacks or
`Backup scheduler run failed:`.

The MCP probe should reject missing/invalid bearer auth and succeed with a
configured inbound client token. Public clients should use the HTTPS URL from
`INVOICES_MCP_PUBLIC_URL`, not the internal Compose URL.

## Runtime Smoke

Use runtime smoke when changing container startup behavior:

```bash
./scripts/runtime_smoke.sh
```

The script builds the runtime image, starts temporary web, scheduler, and MCP
containers with shared `db/` and `media/` mounts, waits for the web and MCP
services, confirms the Django services use `/app/db/db.sqlite3`, and runs an
authenticated MCP probe.

## Database Checks

Confirm the effective database path inside the Django services:

```bash
COMPOSE_PROJECT_NAME=03-invoices docker compose exec web python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings'); import django; django.setup(); from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
COMPOSE_PROJECT_NAME=03-invoices docker compose exec scheduler python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings'); import django; django.setup(); from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
```

Confirm migrations and backup tables exist:

```bash
COMPOSE_PROJECT_NAME=03-invoices docker compose exec web python manage.py showmigrations --plan
COMPOSE_PROJECT_NAME=03-invoices docker compose exec web python -c "import sqlite3; conn = sqlite3.connect('/app/db/db.sqlite3'); print(conn.execute(\"select name from sqlite_master where type='table' and name in ('django_migrations', 'invoices_backupconfiguration', 'invoices_backuprun') order by name\").fetchall())"
```
