## Overview

Preserve the production runtime host contract during the canonical deploy so `invoices.ultramac.work` keeps serving after rollout. The fix should make deploy-time env sourcing explicit, safe, and verifiable instead of depending on manual edits to the deploy worktree `.env`.

## Problem

The issue is still valid against the current tracked deployment flow. `scripts/deploy.sh` sources `.deploy.env`, optionally backfills a small secret set from Phase, and then only syncs `SECRET_KEY` into the runtime `.env`. If that runtime file is missing or recreated, the deploy path can leave `.env` with only `SECRET_KEY`, which makes Django fall back to `ALLOWED_HOSTS=['127.0.0.1', 'localhost']`.

That allows a localhost-only probe to look healthy while breaking the real production host contract:

- requests with `Host: invoices.ultramac.work` return `400 Bad Request`
- the current post-deploy verification probes `http://127.0.0.1:8000/` without the production `Host` header
- operators are forced into manual `.env` hotfixes after deploy

## Proposed Outcome

Treat production host/runtime env as a small deploy-managed contract instead of a partial side effect.

Recommended contract:

1. `SECRET_KEY` and `RENDER_EXTERNAL_HOSTNAME` are required deploy-managed inputs.
2. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are written into the runtime `.env` as deterministic normalized values for the live host, while still allowing explicit extra hosts/origins.
3. Source precedence remains:
   1. explicit shell exports and `.deploy.env`
   2. the existing Phase-backed lookup for missing managed values
   3. no silent fallback for missing required managed values; deploy fails before rollout
4. Writing managed values into the runtime `.env` preserves unrelated existing runtime entries instead of truncating the file.
5. `scripts/verify_deploy.sh` keeps the current stack and scheduler checks, but also probes `127.0.0.1:8000` with the configured production `Host` header.

Assumption: `app/settings.py` already handles the host/origin contract correctly once the expected env values are present, so this issue should focus on deploy sourcing, runtime env sync, verification, docs, and evidence capture.

## Constraints / Non-Goals

- Keep the current Compose deployment shape based on the shared `.env`, `db`, and `media` bind mounts.
- Keep the existing `web` and `scheduler` split and rollout order.
- Keep the existing Phase app/env override knobs; this issue does not require redesigning Phase environments.
- Do not redesign all runtime env management for every setting in the app.
- Do not require manual post-deploy `.env` editing as part of the canonical rollout.
- Do not change the live hostname away from `invoices.ultramac.work`.
- Do not broaden this into unrelated secret-management, database, or artifact-automation work.

## Acceptance Criteria

### User Outcome

1. After a normal Ultramac deploy, `curl -H "Host: invoices.ultramac.work" http://127.0.0.1:8000/` no longer returns `400 Bad Request`.
2. The live app responds for the real production host with an application response, such as the expected anonymous redirect to login, without requiring a manual runtime `.env` hotfix after deploy.

### Technical Behavior

1. The canonical deploy path resolves required managed runtime inputs before rollout and fails early with a clear missing-key error if they are unavailable.
2. The runtime `.env` produced by the deploy flow includes the production host contract:
   1. `RENDER_EXTERNAL_HOSTNAME=invoices.ultramac.work`
   2. `ALLOWED_HOSTS` containing `127.0.0.1`, `localhost`, and `invoices.ultramac.work`
   3. `CSRF_TRUSTED_ORIGINS` containing `https://invoices.ultramac.work`
3. Syncing deploy-managed values into the runtime `.env` preserves unrelated existing runtime entries and does not reduce the file to only `SECRET_KEY`.
4. `scripts/verify_deploy.sh` verifies the real host contract by probing the local web endpoint with the configured production `Host` header while retaining the existing named-stack and scheduler-log checks.

### Operations / Deployment

1. Repository docs identify the authoritative source precedence for production host/runtime values and the one-time operator setup required before deploy.
2. The canonical deploy remains a single tracked repo command and no longer depends on undocumented manual `.env` repair after rollout.
3. The rollout does not change the current Compose stack name, service shape, bind mounts, or migration strategy.

### Validation

1. Automated script-level tests cover successful runtime env sync for the managed host contract.
2. Automated script-level tests cover deploy failure when required managed runtime inputs are missing.
3. Automated script-level tests cover host-aware deploy verification passing for an accepted host and failing for a rejected host.
4. Existing deployment/settings validation continues to prove the current Compose and Django host behavior still works with the updated env contract.
5. A repo-owned Playwright reviewer-evidence command captures the configured host being accepted without depending on seeded data, exact page wording, or incidental DOM structure.

## Implementation Plan

1. Replace the `SECRET_KEY`-only runtime sync in `scripts/deploy.sh` with deploy-managed runtime env logic that:
   1. resolves required inputs from shell/`.deploy.env` with Phase fallback
   2. normalizes the host/origin values for the live host
   3. preserves unrelated existing `.env` entries
   4. aborts before rollout if required managed inputs are missing
2. Mirror the existing preview-style host env pattern for production so the runtime file contains normalized host values instead of relying on manual edits.
3. Update `scripts/verify_deploy.sh` so the HTTP check uses the configured production host header against `127.0.0.1:8000` and fails clearly on host rejection.
4. Expand script-level tests to cover env merge/preservation, missing-key failure, and the host-aware verification path.
5. Add an issue-specific Playwright evidence scenario that records a preview-safe application page after the configured host is accepted.
6. Update deployment docs so operators know where production host/runtime values come from and what post-deploy probe confirms the contract.

## Task List

- [x] Define the deploy-managed runtime host contract
  - [x] Resolve `SECRET_KEY` and `RENDER_EXTERNAL_HOSTNAME` from shell/`.deploy.env` with the existing Phase lookup as fallback for missing managed values.
  - [x] Normalize `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` so the live host and HTTPS origin are always present.
  - [x] Preserve explicit extra hosts/origins from deploy-managed sources without duplicating normalized entries.
  - [x] Fail the deploy before rollout when required managed inputs cannot be resolved.

- [x] Replace the partial runtime `.env` sync
  - [x] Replace `sync_runtime_secret_key` with merge/upsert logic for the managed runtime keys.
  - [x] Preserve unrelated existing runtime `.env` entries while updating the managed keys.
  - [x] Write the runtime env update atomically enough to avoid leaving a truncated file on failure.
  - [x] Add script-level tests for successful sync, preservation, normalization, and missing required inputs.

- [x] Strengthen post-deploy verification
  - [x] Resolve the verification host from explicit verification env, `RENDER_EXTERNAL_HOSTNAME`, or the runtime env file.
  - [x] Update the web probe to send the configured production `Host` header to the local web endpoint.
  - [x] Keep the current service-state, expected container-name, restart-count, and scheduler-log checks.
  - [x] Add tests for host-header verification success, retry behavior, and failure on host rejection.

- [x] Add preview-safe reviewer evidence code
  - [x] Add an issue-specific Playwright spec for the production host/runtime reachability scenario.
  - [x] Capture a full-page screenshot checkpoint after the app responds for the configured review host.
  - [x] Enable video capture through the scenario command without adding brittle text or DOM assertions to the evidence path.
  - [x] Reuse existing Playwright/evidence helpers only explicitly and update them if full-page checkpoint support is needed.

- [x] Align operator documentation with the new contract
  - [x] Document the authoritative source precedence for production host/runtime values.
  - [x] Document the expected host-header probe and non-400 result after deploy.
  - [x] Document that manual post-deploy `.env` hotfixing is not part of the canonical rollout.
  - [x] Keep `README.md` and `project/README.md` consistent about the canonical deploy and verification flow.

## Deployment / Rollout

- This is an operational deploy-script/docs/test/evidence change; no schema migration is expected.
- Before the first live rollout with this fix, operators should ensure the authoritative source selected by the deploy flow includes `SECRET_KEY` and `RENDER_EXTERNAL_HOSTNAME=invoices.ultramac.work`.
- Because the site is currently hotfixed manually, the fixed deploy should rewrite/normalize the runtime `.env`; do not treat the existing manual hotfix as the ongoing source of truth.
- Post-deploy validation should include the canonical verification script and the equivalent manual probe:
  - `curl -H "Host: invoices.ultramac.work" http://127.0.0.1:8000/`
- Expected live result is a non-400 application response, typically the login redirect for an anonymous request.

## File-Level Changes

### Add

- `tests/e2e/production-host-runtime.spec.js` or equivalent issue-specific Playwright evidence spec.
- A small helper under `scripts/` for deploy-managed runtime env merge/validation, if the logic is extracted from `scripts/deploy.sh`.

### Modify

- `scripts/deploy.sh` — resolve, validate, normalize, and sync the managed runtime host contract instead of only syncing `SECRET_KEY`.
- `scripts/verify_deploy.sh` — add a host-aware web probe for the configured production hostname.
- `tests/test_suite.py` — extend script-level coverage for env sync and host-aware verification.
- `tests/e2e/helpers/demo-evidence.js` — update only if needed to support full-page screenshot checkpoints for the issue-specific evidence scenario.
- `README.md` — document the authoritative production host/runtime env source and post-deploy verification contract.
- `project/README.md` — align the managed deployment description with the new runtime env sync behavior.

### Keep

- `app/settings.py` — keep the current `RENDER_EXTERNAL_HOSTNAME`-based host/origin behavior as the application-side contract unless tests expose a settings bug.
- `docker-compose.yml` — keep the current `.env`, `db`, and `media` bind mounts and shared two-service stack shape.
- The existing `03-invoices` Compose project name and web-before-scheduler rollout order.

## Demo Media

### Scenario: production-host-runtime-reachable

#### Repo Command

`PLAYWRIGHT_VIDEO=on OPENCODE_DEMO_SCENARIO=production-host-runtime-reachable ./scripts/e2e.sh tests/e2e/production-host-runtime.spec.js --project=chromium`

#### Outputs

video + screenshots

#### Steps

1. Use the review preview URL when `OPENCODE_PREVIEW_PUBLIC_URL` is provided; otherwise use the local Playwright server started by `./scripts/e2e.sh`.
2. Navigate to the app root using the configured Playwright base URL.
3. Allow normal application redirects to settle for the unauthenticated reviewer-visible state.
4. Capture reviewer evidence after the configured host is accepted and the app renders an application page instead of a host-rejection error.

#### Screenshot Checkpoints

1. `host-contract-accepted` — full-page screenshot of the reviewer-visible application or login page after the configured host is accepted. No focused crop is needed because the full-page state is sufficient evidence that the host was not rejected.

## Open Questions

None.
