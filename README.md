# Invoices

Invoices is a Django application for managing invoices, expenses, payments,
imports, and operational backups. It is designed to run locally for development,
inside Docker for validation, and as a small production Compose stack with a web
service, backup scheduler, and Streamable HTTP MCP service.

## Features

- Customer, project, invoice, payment, and expense workflows.
- Invoice and expense dashboard views with reusable UI components.
- CSV/XLS/XLSX import support for expense and billing data.
- IMAP-only incoming invoice inbox for review-first supplier invoice intake.
- SQLite-friendly production deployment with persistent `db/` and `media/`
  mounts.
- Manual and scheduled backup support for S3-compatible object storage.
- Authenticated Streamable HTTP MCP endpoint for approved AI invoice clients.
- Playwright smoke tests and automation evidence hooks for UI-visible changes.

## Requirements

- Python 3.13.
- Node.js and npm for Playwright smoke tests.
- Docker for container validation, preview builds, and production deployment.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp env.example .env
mkdir -p db media
python manage.py migrate
python manage.py runserver
```

The default local database path from `env.example` is `db/db.sqlite3`.
Runtime databases, media, static build output, Playwright auth state, and
generated exports are intentionally ignored by git.

## Docker

Build a local runtime image:

```bash
docker build -t invoices:local .
```

Run the app with persistent local SQLite and media mounts:

```bash
mkdir -p db media
docker run --rm -p 8000:8000 --env-file .env -e RUN_MIGRATIONS=1 \
  -v "$(pwd)/db:/app/db" \
  -v "$(pwd)/media:/app/media" \
  -v "$(pwd)/.env:/app/.env:ro" \
  invoices:local
```

Run the Compose stack with the web, scheduler, and MCP services:

```bash
docker compose up -d
```

`./scripts/deploy.sh` is the canonical live deployment entrypoint. It runs the
tracked `docker compose` rollout for the canonical `03-invoices` stack, using
`03-invoices` as the canonical stack name so the live containers are predictable
as `03-invoices-web-1`, `03-invoices-scheduler-1`, and
`03-invoices-mcp-1`. The deploy path should not require any separate manual
container recreation commands; it updates all services together under the same
Compose project, exports
`COMPOSE_PROJECT_NAME=03-invoices`, derives one `INVOICES_IMAGE` reference for
all services, runs `docker compose pull web scheduler mcp`, and recreates `web`
before `scheduler` and `mcp`.

Post-deploy verification checks that all services are running under the same
`03-invoices` Compose project, confirms the expected `03-invoices-web-1`,
`03-invoices-scheduler-1`, and `03-invoices-mcp-1` container names, verifies
`http://127.0.0.1:8000/` responds successfully, and fails if scheduler startup
logs contain `Traceback (most recent call last):` or
`Backup scheduler run failed:`. It also probes the MCP Streamable HTTP endpoint
for missing/invalid auth rejection and authenticated tool discovery. Operators
can inspect the same stack with `COMPOSE_PROJECT_NAME=03-invoices docker compose
ps web scheduler mcp`, a `python3 -c` health probe, `docker compose logs
--no-color --tail 50 scheduler`, and `docker compose logs --no-color --tail 50
mcp`.

Deployment rollout verification summary:

- runs the tracked `docker compose` rollout for the canonical `03-invoices` stack
- `03-invoices` as the canonical stack name
- `03-invoices-web-1` and `03-invoices-scheduler-1`
- `03-invoices-web-1`, `03-invoices-scheduler-1`, and `03-invoices-mcp-1`
- should not require any separate manual container recreation commands
- updates both services together under the same Compose project
- updates all services together under the same Compose project
- exports `COMPOSE_PROJECT_NAME=03-invoices`
- derives one `INVOICES_IMAGE` reference for both services
- derives one `INVOICES_IMAGE` reference for all services
- runs `docker compose pull web scheduler`
- runs `docker compose pull web scheduler mcp`
- recreates `web` before `scheduler`
- recreates `web` before `scheduler` and `mcp`
- checks that both services are running under the same `03-invoices` Compose project
- checks that all services are running under the same `03-invoices` Compose project
- confirms the expected `03-invoices-web-1` and `03-invoices-scheduler-1` container names
- confirms the expected `03-invoices-web-1`, `03-invoices-scheduler-1`, and `03-invoices-mcp-1` container names
- verifies `http://127.0.0.1:8000/` responds successfully
- verifies authenticated MCP protocol reachability and invalid-auth rejection
- fails if scheduler startup logs contain `Traceback (most recent call last):` or `Backup scheduler run failed:`
- COMPOSE_PROJECT_NAME=03-invoices docker compose ps web scheduler mcp
- python3 -c
- docker compose logs --no-color --tail 50 scheduler
- docker compose logs --no-color --tail 50 mcp

## Validation

```bash
python manage.py check
python manage.py test
./scripts/ci.sh
./scripts/e2e.sh
```

`scripts/ci.sh` is the canonical Docker-based validation command used by the
automation controller. `scripts/e2e.sh` is the repo-owned Playwright smoke
entrypoint; automation runs it through the shared Playwright evidence runner
image instead of installing browsers in workflow YAML.

Issue 42 acceptance evidence is explicit in the tracked rollout and validation:

- Running the canonical deployment command updates the live invoices deployment without requiring undocumented manual container recreation commands
- The live rollout updates both `web` and `scheduler` as one Docker Compose stack
- The live rollout also updates `mcp` as part of the same Docker Compose stack
- Operators have a short documented verification path that confirms both services are healthy after rollout
- Operators can also verify the MCP service with the authenticated protocol probe
- `scripts/deploy.sh` performs the tracked `docker compose` rollout step after image publication
- The tracked rollout uses a stable explicit Compose project name of `03-invoices` by default on Ultramac
- The resulting live container names are predictable under that project name, including `03-invoices-web-1` and `03-invoices-scheduler-1`
- The MCP container name is also predictable under that project name, including `03-invoices-mcp-1`
- The Compose configuration accepts an explicit image reference or tag so both services are recreated from the intended release image
- The Compose configuration uses the same explicit image reference or tag for the MCP service
- The rollout preserves the current bind-mounted `.env`, `db`, and `media` paths already used by the deployment
- The rollout order minimizes scheduler startup racing migrations by ensuring the web service performs migration-bearing startup before the scheduler is recreated or started
- Repository deployment docs match the actual tracked rollout behavior
- The canonical deploy path includes verification of both services after rollout
- The canonical deploy path includes MCP service verification after rollout
- The production rollout no longer depends on undocumented manual container handling
- Manual Compose inspection commands used during operations resolve to the same named stack as the tracked deploy flow
- Validation covers the tracked rollout script behavior for the named Compose stack and both services
- Validation covers MCP rollout behavior for the named Compose stack
- Validation confirms the compose invocation targets `03-invoices` consistently
- Validation confirms both services are recreated against the intended image reference during rollout logic or equivalent scripted verification
- Validation confirms the MCP service is recreated against the intended image reference during rollout logic or equivalent scripted verification
- Validation confirms post-deploy verification checks both web responsiveness and scheduler startup state
- Validation confirms post-deploy verification checks MCP authenticated reachability

## Documentation

- [Documentation index](docs/README.md) explains what each project document is
  for.
- [API](docs/api.md) covers token setup, authentication headers, endpoint
  examples, filters, errors, reports, PDFs, and expense uploads.
- [Development](docs/development.md) covers repo structure, local setup,
  environment values, generated files, and tests.
- [Deployment](docs/deployment.md) covers Docker/Compose rollout and
  verification.
- [MCP server](docs/mcp-server.md) covers Streamable HTTP operation, token
  setup, endpoint configuration, artifact limits, client examples, and checks.
- [Backups](docs/backups.md) covers backup configuration, scheduler behavior,
  locking, object keys, and operator checks.
- [Incoming invoice inbox](docs/incoming-invoice-inbox.md) covers IMAP setup,
  credential references, polling and fixture imports, review/paid conversion,
  unpaid limitations, currency metadata, privacy, and rollback guidance.
- [Automation](docs/automation.md) covers the Gitea/OpenCode integration
  contract, previews, evidence, and production artifacts.
- Historical task specs live under [docs/specs/issues](docs/specs/issues/).
- UI foundations and design intent live in [DESIGN.md](DESIGN.md).

## License

This project is licensed under the [MIT License](LICENSE).
