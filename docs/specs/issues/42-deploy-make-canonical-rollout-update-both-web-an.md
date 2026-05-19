# Overview

Make `scripts/deploy.sh` the canonical live rollout entrypoint for Ultramac by having it update the real Docker Compose deployment, not just publish images. The rollout must manage the existing `web` and `scheduler` services together under one explicit stable Compose project name such as `03-invoices`.

# Problem

The repository already defines a two-service production shape in `docker-compose.yml`, and the README documents running both `web` and `scheduler`. However, `scripts/deploy.sh` currently stops after `scripts/build_and_push.sh`, so the tracked deploy path does not actually recreate the live containers.

This leaves production rollout dependent on manual server-side Compose/container steps and does not guarantee that both services move to the same image release together. It also leaves stack naming inconsistent on Ultramac because invoices is not deployed under an explicit indexed Compose project name.

# Proposed Outcome

`scripts/deploy.sh` should own the full tracked rollout flow for Ultramac:

1. build and push the release image;
2. set the canonical Compose project name to `03-invoices` by default;
3. run the Docker Compose update against the existing two-service stack;
4. recreate both `web` and `scheduler` from the intended image reference while preserving the current `.env`, `db`, and `media` bind mounts;
5. run lightweight post-deploy verification for both services.

The Compose configuration should support an explicit image reference/tag input and default to the stable project name so both the deploy script and any manual verification commands resolve to the same stack and predictable container names.

# Constraints / Non-Goals

- Do not change the production service shape beyond the existing `web` and `scheduler` services.
- Do not change the existing Ultramac bind-mounted paths for `.env`, `db`, or `media`.
- Do not expand this issue into fixing unrelated image/runtime bugs.
- Do not introduce separate ad hoc runtime handling outside tracked repository scripts.
- Do not require operators to manage `web` and `scheduler` as separate stacks.
- Do not add unrelated application, migration, or backup feature work.

# Acceptance Criteria

## User Outcome

1. Running the canonical deployment command updates the live invoices deployment without requiring undocumented manual container recreation commands.
2. The live rollout updates both `web` and `scheduler` as one Docker Compose stack.
3. Operators have a short documented verification path that confirms both services are healthy after rollout.

## Technical Behavior

1. `scripts/deploy.sh` either performs or delegates to a tracked script that runs the live `docker compose` rollout step after image publication.
2. The tracked rollout uses a stable explicit Compose project name of `03-invoices` by default on Ultramac.
3. The resulting live container names are predictable under that project name, including `03-invoices-web-1` and `03-invoices-scheduler-1`.
4. The Compose configuration accepts an explicit image reference or tag so both services are recreated from the intended release image.
5. The rollout preserves the current bind-mounted `.env`, `db`, and `media` paths already used by the deployment.
6. The rollout order minimizes scheduler startup racing migrations by ensuring the web service performs migration-bearing startup before the scheduler is recreated or started.

## Operations / Deployment

1. Repository deployment docs match the actual tracked rollout behavior.
2. The canonical deploy path includes verification of both services after rollout.
3. The production rollout no longer depends on undocumented manual container handling.
4. Manual Compose inspection commands used during operations resolve to the same named stack as the tracked deploy flow.

## Validation

1. Validation covers the tracked rollout script behavior for the named Compose stack and both services.
2. Validation confirms the compose invocation targets `03-invoices` consistently.
3. Validation confirms both services are recreated against the intended image reference during rollout logic or equivalent scripted verification.
4. Validation confirms post-deploy verification checks both web responsiveness and scheduler startup state.

# Implementation Plan

1. Update the Compose configuration so the stack has a stable default name and the image reference can be injected cleanly by the deploy path.
2. Extend `scripts/deploy.sh` so it no longer exits after image push and instead runs the canonical Compose rollout for the live stack.
3. Sequence the rollout to reduce migration races: publish image, refresh the `web` service first, then refresh `scheduler` within the same Compose project.
4. Add a lightweight verification step that checks Compose service status, confirms both expected containers are present under `03-invoices`, verifies the web service responds, and verifies the scheduler process started cleanly.
5. Update deployment documentation so the documented command, stack name, and verification commands match the tracked rollout.

# Task List

- [x] Make Compose stack naming and image selection explicit
  - [x] Update `docker-compose.yml` to default the project name to `03-invoices`.
  - [x] Update `docker-compose.yml` to consume an explicit image reference or tag variable suitable for deploy-time rollout.
  - [x] Confirm the existing `web` and `scheduler` services keep the current shared `.env`, `db`, and `media` mounts.

- [x] Extend the canonical deploy script to perform the live rollout
  - [x] Update `scripts/deploy.sh` to export the canonical Compose project name for the rollout.
  - [x] Update `scripts/deploy.sh` to continue from image publication into tracked `docker compose` update commands.
  - [x] Sequence the Compose update so `web` is refreshed before `scheduler` to avoid migration-related startup races.
  - [x] Ensure the rollout recreates both services from the same intended image reference.

- [x] Add deployment verification behavior
  - [x] Add a tracked verification step in the deploy flow or a tracked helper invoked by it that checks the named stack and both services.
  - [x] Verify the web service responds successfully after rollout.
  - [x] Verify the scheduler service is running cleanly after rollout.
  - [x] Add or update script-level validation covering project-name usage and both-service rollout behavior.

- [x] Align operator documentation with the tracked rollout
  - [x] Update `README.md` deployment instructions to describe `scripts/deploy.sh` as the full live rollout path.
  - [x] Document the canonical stack name `03-invoices` and predictable container names for operations and troubleshooting.
  - [x] Document the post-deploy verification commands for both `web` and `scheduler`.

# Deployment / Rollout

This is an operational rollout change, not an application schema change. No new data migration is expected beyond the existing startup migrations already performed by the `web` container.

Rollout expectations:

1. Ultramac should run the tracked deploy entrypoint from the repository checkout that already contains the production `.env`, `db`, and `media` bind mounts.
2. The deploy path should recreate the live Compose stack under `03-invoices` and leave operators with one consistent stack name for inspection and restart commands.
3. Verification should include both `docker compose ps`-style stack checks and an HTTP response check for the web app.
4. If the stack was previously created under an unnamed/default project, the first canonical rollout may replace old container names with the `03-invoices-*` naming convention; docs should make that expected.
5. No separate scheduler-only rollout should be required after the canonical deploy completes.

# File-Level Changes

## Add

- `scripts/` helper for tracked Compose rollout and/or post-deploy verification, if `scripts/deploy.sh` is kept as a thin orchestrator.

## Modify

- `scripts/deploy.sh` — extend from image publication into full named-stack rollout and verification.
- `docker-compose.yml` — set the canonical project name default and make deploy-time image selection explicit for both services.
- `README.md` — align deployment instructions, stack naming, and verification guidance with the real rollout.
- `project/README.md` — update the managed automation description so `scripts/deploy.sh` is described as the canonical live rollout entrypoint rather than image publication only.

## Keep

- Existing `web` and `scheduler` service split.
- Existing bind-mounted `.env`, `db`, and `media` deployment shape.
- Existing startup-migration model where `web` runs migrations and `scheduler` does not.

# Open Questions

None.
