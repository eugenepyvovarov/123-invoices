# Overview

Fix the tracked container deployment path so the production image can be built from the repository Dockerfile and started in the current Ultramac bind-mount shape without one-off Dockerfile edits or runtime `DATABASE_URL` overrides.

# Problem

The current repo-backed deployment path has two concrete failures:

1. The runtime Docker stage fails while preparing `/app/db` and `/app/media`, so the production image cannot be built reliably from the tracked Dockerfile.
2. Production still honors a stale `DATABASE_URL=sqlite:////tmp/db.sqlite3`, which overrides the mounted persistent SQLite path and can send the app to an internal temporary database instead of `/app/db/db.sqlite3`.

That combination breaks the expected deployment contract for both the web and scheduler containers and forces manual workarounds during release.

# Proposed Outcome

Make the containerized SQLite deployment path explicit and safe:

- The runtime image builds successfully from the tracked `Dockerfile`.
- The container startup path treats `/app/db/db.sqlite3` as the default persistent SQLite location for the current bind-mounted deployment shape.
- A stale internal-temp SQLite `DATABASE_URL` no longer wins over the mounted production DB path in this deployment mode.
- Web and scheduler containers both resolve to the same mounted DB and media paths.
- Deployment docs and validation steps describe the correct precedence clearly enough that operators can verify they are using the real persistent DB after rollout.

Recommended scope cut:

- Fix the runtime image filesystem/user setup in the Docker runtime stage.
- Normalize runtime DB path resolution for the current SQLite container deployment.
- Update deployment docs and add a repeatable runtime smoke-validation path.
- Do not broaden this issue into higher-level rollout automation.

# Constraints / Non-Goals

- Keep the current deployment shape based on bind-mounted `/app/db` and `/app/media`.
- Keep SQLite as the supported production database for this issue’s deployment mode.
- Do not redesign the overall deployment pipeline, registry publishing flow, or host orchestration.
- Do not remove support for explicit non-SQLite `DATABASE_URL` usage when operators intentionally provide an external database.
- Do not change local test/CI behavior away from the existing Docker `test` target unless needed to preserve compatibility.
- Do not bundle unrelated infra cleanup into this fix.

# Acceptance Criteria

## User Outcome

1. Operators can build and run the tracked production image without custom Dockerfile edits or manual `DATABASE_URL` overrides.
2. The deployed web container uses the persistent mounted SQLite database at `/app/db/db.sqlite3` in the current SQLite deployment mode.
3. The deployed scheduler container uses the same mounted SQLite database and shared `/app/media` path as the web container.

## Technical Behavior

1. Building the runtime image from the repository `Dockerfile` succeeds in the intended production shape.
2. The runtime startup path creates or uses `/app/db` and `/app/media` safely under the runtime user model.
3. In the current containerized SQLite deployment mode, effective database resolution does not fall back to `/tmp/db.sqlite3` because of the known stale production env value.
4. An explicitly provided external/non-SQLite `DATABASE_URL` continues to work as an override.
5. Existing local CI/test image behavior remains functional.

## Operations / Deployment

1. Deployment documentation states the expected SQLite path, the precedence rules, and that operators should not rely on `sqlite:////tmp/db.sqlite3` in production.
2. The documented web and scheduler startup shape uses the same mounted DB and media paths.
3. Post-deploy verification steps allow operators to confirm migrations and backup-related tables are visible from the mounted persistent DB, not an internal temporary file.

## Validation

1. Validation covers building the runtime image successfully.
2. Validation covers starting a web container against a mounted `/app/db` and `/app/media` path.
3. Validation covers starting a scheduler container against the same mounted paths.
4. Validation confirms the effective DB path inside the running container resolves to the persistent mounted SQLite file.
5. Validation confirms existing Django tests or Docker `test` target behavior still passes after the change.

# Implementation Plan

1. Update the runtime Docker stage so required application and mount directories are created with a user/ownership pattern that works reliably on the target host.
2. Tighten container startup or settings resolution so the current SQLite deployment mode defaults to `/app/db/db.sqlite3` and does not let the known stale `/tmp` SQLite value win unintentionally.
3. Preserve intentional `DATABASE_URL` override behavior for external databases while making the bind-mounted SQLite path canonical for this deployment mode.
4. Add a repeatable runtime smoke-validation path that builds the runtime image and starts both web and scheduler containers against temporary mounted `db/` and `media/` directories.
5. Update deployment documentation so the expected env configuration, DB precedence, and post-deploy verification steps are explicit.

# Task List

- [x] Fix runtime image filesystem setup
  - [x] Update the runtime Docker stage to create `/app/db` and `/app/media` in a way that builds reliably on the production host.
  - [x] Ensure runtime ownership/permissions allow the non-root app user to use mounted DB and media paths.
  - [x] Validate that the runtime image still starts through `entrypoint.sh` after the Docker changes.

- [x] Make mounted SQLite path the safe production default
  - [x] Update runtime DB resolution so the containerized SQLite deployment path defaults to `/app/db/db.sqlite3`.
  - [x] Add a guard for the known stale internal-temp SQLite env value so it does not override the mounted production DB unintentionally.
  - [x] Preserve explicit external-database `DATABASE_URL` behavior.
  - [x] Add focused tests for DB path precedence and container-start env handling.

- [x] Add runtime deployment validation
  - [x] Add a repeatable script or documented command path to build the runtime image and start a web container with mounted `db/` and `media/`.
  - [x] Extend that validation to start the scheduler container against the same mounts.
  - [x] Add validation that inspects the running app/container state to confirm the effective DB path is `/app/db/db.sqlite3`.
  - [x] Re-run existing Docker test-target validation to confirm no CI/test regression.

- [x] Update operator documentation
  - [x] Document the correct production SQLite path and env precedence for bind-mounted container deployments.
  - [x] Document that web runs migrations against the mounted DB and scheduler must share the same DB/media mounts.
  - [x] Document post-deploy checks for confirming migrations and backup tables are visible from the persistent DB.

# Deployment / Rollout

- This is a code-and-config rollout with no schema migration expected from the deployment fix itself.
- Before live rollout, build the runtime image from the tracked repo and run the runtime smoke validation against mounted temporary `db/` and `media/` directories.
- For the current SQLite deployment mode, remove reliance on `DATABASE_URL=sqlite:////tmp/db.sqlite3`; the live configuration should resolve to `/app/db/db.sqlite3`.
- After deploy, verify:
  - the web container starts and runs migrations,
  - the scheduler container starts with the same mounts,
  - the effective DB path is the mounted SQLite file,
  - backup-related tables remain visible from the running containers.

# File-Level Changes

## Add

- `docs/specs/issues/41-deploy-fix-production-image-runtime-path-for-per.md`
- a runtime smoke-validation script under `scripts/` for build/start verification of the production image

## Modify

- `Dockerfile`
- `entrypoint.sh`
- `app/settings.py`
- `README.md`
- `docker-compose.yml`
- relevant test coverage under `invoices/tests/`
- optionally existing validation scripts under `scripts/` if the runtime smoke check is integrated there

## Keep

- `scripts/ci.sh` and `scripts/coverage.sh` as the canonical test-target validation entrypoints
- the current split between `web` and `scheduler` services
- bind-mounted `/app/db` and `/app/media` as the current production deployment shape

# Open Questions

None.
