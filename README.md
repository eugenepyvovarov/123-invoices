# Invoices

Invoices is a Django application for managing invoices, expenses, payments,
imports, and operational backups. It is designed to run locally for development,
inside Docker for validation, and as a small production Compose stack with a web
service plus a backup scheduler.

## Features

- Customer, project, invoice, payment, and expense workflows.
- Invoice and expense dashboard views with reusable UI components.
- CSV/XLS/XLSX import support for expense and billing data.
- SQLite-friendly production deployment with persistent `db/` and `media/`
  mounts.
- Manual and scheduled backup support for S3-compatible object storage.
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
docker run --rm -p 8000:8000 --env-file .env -e RUN_MIGRATIONS=1 \
  -v "$(pwd)/db:/app/db" \
  -v "$(pwd)/media:/app/media" \
  -v "$(pwd)/.env:/app/.env:ro" \
  invoices:local
```

Run the Compose stack with the web and scheduler services:

```bash
docker compose up -d
```

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

## Documentation

- [Documentation index](docs/README.md) explains what each project document is
  for.
- [Development](docs/development.md) covers repo structure, local setup,
  environment values, generated files, and tests.
- [Deployment](docs/deployment.md) covers Docker/Compose rollout and
  verification.
- [Backups](docs/backups.md) covers backup configuration, scheduler behavior,
  locking, object keys, and operator checks.
- [Automation](docs/automation.md) covers the Gitea/OpenCode integration
  contract, previews, evidence, and production artifacts.
- Historical task specs live under [docs/specs/issues](docs/specs/issues/).
- UI foundations and design intent live in [DESIGN.md](DESIGN.md).

## License

This project is licensed under the [MIT License](LICENSE).
