# Overview

Configure Gitea Actions cache end-to-end for this repository’s active runner, then use that cache in the Playwright workflow so Python and Node dependencies no longer download from scratch on every run. The recommended cut is to finish the runner cache plumbing on Ultramac first, then add `pip` caching in `playwright.yml`, confirm existing `npm` caching works under Gitea, and document why Docker-based validation stays out of scope here.

# Problem

The current CI path pays repeated dependency setup cost, especially in the Playwright smoke workflow. Although `playwright.yml` already enables `actions/setup-node` npm caching, the active `gitea-act-runner` deployment on Ultramac appears incomplete for `actions/cache` compatibility: `cache.enabled: true` is already set in the authoritative runner config, but `cache.host` and `cache.port` are not defined and the runner container does not publish a cache port. That means `actions/setup-python` and `actions/setup-node` cache restore/save behavior is unlikely to be reliable from job containers until the runner cache service is explicitly reachable.

# Proposed Outcome

After this work:

- the active runner cache configuration on Ultramac is explicitly reachable from job containers via configured `cache.host` and `cache.port`
- the `gitea-act-runner` container publishes the cache port used by the runner config
- `.gitea/workflows/playwright.yml` adds `actions/setup-python` pip caching keyed from `requirements.txt`
- `.gitea/workflows/playwright.yml` keeps npm caching enabled through `actions/setup-node`
- workflow logs demonstrate cache restore/save behavior for Playwright dependency setup after cache warm-up
- at least one non-Playwright workflow is evaluated for the same pattern, with `pr-tests.yml` documented as a non-match because validation runs through `docker build` rather than workflow-level dependency setup
- repository documentation explains the Ultramac runner prerequisite, verification method, and follow-up options if package-manager caching is still insufficient

# Constraints / Non-Goals

- Do not add Playwright browser-binary caching in this issue.
- Do not redesign `pr-tests.yml`, `scripts/ci.sh`, or `Dockerfile` to add Docker layer caching here.
- Do not treat `cache.enabled: true` alone as sufficient runner validation.
- Do not expand this issue into prebuilt Playwright CI images or custom runner-label work; keep those as follow-up options.
- Do not rely on undocumented assumptions about the runner cache endpoint; the live Ultramac runner config is the source of truth.

# Acceptance Criteria

## User Outcome

1. Playwright CI runs stop paying full Python dependency download cost on every run after the cache is warmed.
2. Maintainers can identify the authoritative runner cache config for this repository and know how to verify future cache hits from workflow logs.
3. The issue documents whether the same pattern applies outside Playwright and why any evaluated workflow was kept unchanged.

## Technical Behavior

1. The active `gitea-act-runner` deployment uses an explicit `cache.host` and `cache.port` in `/Users/eugene/www/02-gitea/act_runner/config.yaml`.
2. The `gitea-act-runner` container publishes the configured cache port so job containers can reach the cache service.
3. `.gitea/workflows/playwright.yml` configures `actions/setup-python@v5` with `cache: pip` and the dependency file path for `requirements.txt`.
4. `.gitea/workflows/playwright.yml` preserves `actions/setup-node@v4` npm caching.
5. The evaluated non-Playwright workflow outcome is documented, including why `pr-tests.yml` does not adopt workflow-level pip/npm caching in this issue.

## Operations / Deployment

1. Runner cache connectivity is verified after the runner config and container port changes are applied.
2. Runner restart steps and any deployment-specific cache networking assumptions are documented.
3. Rollout guidance identifies the expected cache restore/save signals in Gitea Actions logs for both pip and npm.

## Validation

1. A cold-cache Playwright run succeeds with the updated runner and workflow configuration.
2. A subsequent comparable Playwright run shows pip cache restore evidence in logs.
3. Existing npm cache behavior in Playwright is confirmed from logs after runner cache connectivity is fixed.
4. The documented `pr-tests.yml` evaluation matches the current `scripts/ci.sh` and `Dockerfile` behavior.

# Implementation Plan

1. Update the authoritative Ultramac runner config at `/Users/eugene/www/02-gitea/act_runner/config.yaml` to define explicit cache networking values in addition to the existing `cache.enabled: true`.
2. Update the `gitea-act-runner` container deployment so the same cache port is published from the container.
3. Restart the runner and validate that Gitea job containers can restore/save cache entries through workflow logs.
4. Add `cache: pip` to `actions/setup-python` in `.gitea/workflows/playwright.yml`, keyed from `requirements.txt`, while preserving npm caching in `actions/setup-node`.
5. Run or inspect two comparable Playwright workflow executions to distinguish cold-cache population from warm-cache restore behavior.
6. Review `.gitea/workflows/pr-tests.yml`, `scripts/ci.sh`, and `Dockerfile` to document why this issue stops at package-manager caches for Playwright rather than changing the Docker-based validation path.
7. Add concise CI documentation covering the Ultramac runner prerequisite, verification steps, and follow-up options such as direct `actions/cache`, Docker layer caching, or a prebuilt CI image.

# Task List

- [x] Complete runner cache plumbing on Ultramac
  - [x] Add explicit `cache.host` to `/Users/eugene/www/02-gitea/act_runner/config.yaml`.
  - [x] Add explicit `cache.port` to `/Users/eugene/www/02-gitea/act_runner/config.yaml`.
  - [x] Publish the same cache port from the `gitea-act-runner` container deployment.
  - [x] Restart the runner and capture the expected cache connectivity evidence from workflow logs.

- [x] Update and validate Playwright dependency caching
  - [x] Add `cache: pip` and the `requirements.txt` dependency path to the `actions/setup-python` step in `.gitea/workflows/playwright.yml`.
  - [x] Keep the existing `actions/setup-node` npm cache configuration unchanged in `.gitea/workflows/playwright.yml`.
  - [x] Verify a cold-cache Playwright run still completes successfully.
  - [x] Verify a subsequent Playwright run shows pip restore behavior and confirm npm cache restore/save behavior in logs.

- [x] Evaluate non-Playwright workflow applicability
  - [x] Review `.gitea/workflows/pr-tests.yml` to confirm it does not install Python or Node dependencies through setup-action steps.
  - [x] Review `scripts/ci.sh` to confirm validation is driven by `docker build` and `docker run`.
  - [x] Review `Dockerfile` to confirm Python dependencies are installed during image build.
  - [x] Document the recommendation to keep `pr-tests.yml` unchanged in this issue and defer Docker-layer caching to follow-up work if needed.

- [x] Document verification and future options
  - [x] Add CI documentation describing the authoritative Ultramac runner config and cache networking prerequisite.
  - [x] Add log-based verification guidance for cold-cache versus warm-cache behavior for pip and npm.
  - [x] Add a short note on other Gitea caching options after runner cache networking works.
  - [x] Add the explicit evaluation outcome for `pr-tests.yml` so the non-change is visible to future maintainers.

# Deployment / Rollout

Rollout should happen in this order:

1. Apply the runner cache config change on Ultramac.
2. Publish the cache port from the `gitea-act-runner` container and restart the runner.
3. Confirm cache connectivity from workflow logs before relying on workflow-level caching.
4. Merge the Playwright workflow update.
5. Run one cold-cache Playwright job to populate caches.
6. Run a second comparable Playwright job to confirm restore behavior.

There are no database or user-facing rollout impacts. The main operational risk is declaring workflow caching before the runner cache service is actually reachable.

# File-Level Changes

## Add

- CI cache guidance under `docs/` if no existing CI documentation location is appropriate

## Modify

- `.gitea/workflows/playwright.yml` — add pip caching and preserve npm caching
- `README.md` or CI-focused docs — document the Ultramac runner cache prerequisite, verification steps, and evaluated alternatives
- `docs/specs/issues/27-configure-gitea-actions-cache-and-pip-npm-cachin.md` — align the tracked issue spec with the clarified runner deployment requirement
- Ultramac runner operations: `/Users/eugene/www/02-gitea/act_runner/config.yaml` — define explicit cache host/port
- Ultramac runner container deployment for `gitea-act-runner` — publish the configured cache port

## Keep

- `.gitea/workflows/pr-tests.yml` — evaluated but not changed to workflow-level pip/npm caching in this issue
- `scripts/ci.sh` — keep Docker-based validation entrypoint
- `Dockerfile` — keep dependency installation inside the image build for this issue

# Open Questions

None.
