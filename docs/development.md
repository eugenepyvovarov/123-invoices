# Development

## Repository Layout

- `app/`: Django settings, root URL configuration, and WSGI/ASGI entrypoints.
- `accounts/`: authentication, profile settings, OTP/recovery flow, and related
  tests.
- `invoices/`: invoices, customers, projects, payments, imports, backups,
  shared services, templates, static assets, and most domain tests.
- `expenses/`: expense list/import views, forms, templates, and tests.
- `tests/e2e/`: Playwright smoke tests and helpers.
- `scripts/`: validation, preview, artifact, deploy, and utility entrypoints.
- `docs/specs/issues/`: historical AI specs for completed or in-flight tasks.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp env.example .env
mkdir -p db media
python manage.py migrate
python manage.py runserver
```

Install Node dependencies only when Playwright smoke tests are needed:

```bash
npm ci
```

## Environment

`env.example` is the committed reference. Copy it to untracked `.env` and adjust
local values there.

Important values:

- `SECRET_KEY`: required by Django.
- `DEBUG`: use `1` for local development and `0` outside development.
- `DB_PATH`: recommended local value is `db/db.sqlite3`.
- `DATABASE_URL`: optional intentional external database override.
- `MEDIA_ROOT`: recommended local value is `media`.
- `ALLOWED_HOSTS`: defaults to `127.0.0.1,localhost`.
- `BACKUP_SCHEDULING_TIMEZONE`: optional locally; set explicitly in production
  when scheduled backups should follow a business timezone.

For SQLite deployments, prefer `DB_PATH` plus persistent mounts over
`DATABASE_URL`.

## Validation

Quick Django sanity check:

```bash
DEBUG=1 SECRET_KEY=dev-check DB_PATH=/tmp/invoices-check.sqlite3 python manage.py check
```

Run Django tests locally:

```bash
python manage.py test
```

Run the canonical Docker validation path:

```bash
./scripts/ci.sh
```

Run coverage in the same Docker test target:

```bash
./scripts/coverage.sh
```

Run the Playwright smoke suite:

```bash
./scripts/e2e.sh
```

`scripts/e2e.sh` prepares an E2E SQLite database, optional seed data, and
Playwright auth state under `tmp/`. In automation, the same script is executed
inside the shared Playwright evidence runner image.

## Generated Files

Do not commit local runtime or generated artifacts:

- `.env` and `.deploy.env`.
- `db.sqlite3`, `db/e2e.sqlite3`, and `db/e2e-runtime.sqlite3`.
- SQLite files under `db/`; keep only `db/.gitkeep`.
- `media/`.
- `staticfiles/`, except `staticfiles/.gitkeep`.
- `tmp/`, except `tmp/.gitkeep`.
- `node_modules/`, `test-results/`, `playwright-report/`, screenshots, videos,
  and exports.
- `*.profraw`.

If tests need durable data, add sanitized fixtures under a test fixture folder.
Do not use local runtime databases, exported invoices, browser auth state, or
customer data as fixtures.

## UI Conventions

- Follow [DESIGN.md](../DESIGN.md) for shared UI patterns.
- Use existing CSS tokens and component classes before adding new styles.
- Use Tabler Icons for added or changed UI icons.
- Use Pico.css grouped components for filter/action groups.
- Use Charts.css for charts unless the task explicitly changes that choice.
- Keep monetary amounts formatted with two decimal places.
