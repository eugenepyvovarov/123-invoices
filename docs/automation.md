# Automation

## Boundary

This repository is managed by the OpenCode Gitea automation controller. The app
repository owns commands and app-specific behavior. The controller owns issue
state, persona behavior, workflow orchestration, shared runner images, and
review/evidence policy.

Do not edit managed automation files during ordinary product work. Change them
only for explicit automation setup, chore synchronization, workflow behavior,
repo onboarding, preview, evidence, deployment, or artifact tasks.

## Managed Files

Automation integration points:

- `.gitea/workflows/`
- `project/opencode-managed.json`
- `project/README.md`
- `scripts/opencode`
- `scripts/lib/opencode-managed-workflow-context.py`
- `scripts/ci.sh`
- `scripts/coverage.sh`
- `scripts/e2e.sh`
- `scripts/preview.sh`
- `scripts/destroy-preview.sh`
- `scripts/artifact.sh`
- `scripts/deploy.sh`
- `scripts/verify_deploy.sh`
- `scripts/runtime_smoke.sh`

## Validation Contract

`project/opencode-managed.json` declares the command contracts consumed by the
controller:

- validation: `/bin/bash ./scripts/ci.sh`
- coverage: `/bin/bash ./scripts/coverage.sh`
- Playwright smoke: `/bin/bash ./scripts/e2e.sh`
- deployment: `/bin/bash ./scripts/deploy.sh`
- production artifact: `/bin/bash ./scripts/artifact.sh production`

`scripts/ci.sh` builds the Docker `test` target, runs Django tests, and performs
a runtime smoke check for web/scheduler startup. `scripts/coverage.sh` runs
coverage inside the same Docker test target.

## Playwright And Evidence

`scripts/e2e.sh` is the repo-owned Playwright smoke command. It supports local
execution, preview-backed execution, and controller evidence execution.

Automation runs web Playwright smoke/evidence through the shared Playwright
runner image. Do not add workflow-level `actions/setup-python`,
`actions/setup-node`, `npx playwright install`, or browser dependency bootstrap
back into managed workflows. If runtime becomes slow, improve Docker/shared
runner caching instead.

## Preview Contract

Preview automation uses:

- `scripts/artifact.sh preview`
- `scripts/preview.sh`
- `scripts/destroy-preview.sh`

Normal previews use the PR branch checkout. Baseline visual captures may set
`OPENCODE_PREVIEW_REF`; preview scripts must build and run from that exact
commit in an isolated detached worktree rather than silently using branch head.

Demo evidence and visual validation should target the preview URL supplied by
automation. The repo should not start a second unrelated app instance when a
preview URL is available.

## Production Artifact Contract

Post-merge publication uses:

```bash
./scripts/artifact.sh production
```

The command publishes the production image and writes JSON to stdout with a
`published_artifacts` field. The controller uses that result to decide whether a
merged issue can be closed as fully delivered.

## Design Contract

`DESIGN.md` is present and useful as an app-level UI contract. In
`project/opencode-managed.json`, design-contract linting is currently not a
required automation gate. Treat it as guidance unless a task explicitly enables
or requires design-contract validation.

## Historical Specs

Task-specific AI specs live under `docs/specs/issues/`. They are retained for
history and review context, but current setup and operations should be
documented in `README.md` and the focused docs under `docs/`.
