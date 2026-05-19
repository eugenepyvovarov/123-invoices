# Automation Contract

This directory contains repository-local configuration for the OpenCode Gitea
automation controller.

## Files

- `opencode-managed.json`: the controller contract for validation, review,
  preview, Playwright smoke, visual validation, deployment, and production
  artifact publication.

## Ownership

The application repository owns the scripts referenced by
`opencode-managed.json`. The automation controller owns workflow orchestration,
persona instructions, issue state transitions, shared runner images, and review
policy.

Do not treat this directory as product documentation. Product setup lives in
the root README and `docs/`. Automation behavior is summarized in
`docs/automation.md`.

## Current Command Contracts

- Validation: `/bin/bash ./scripts/ci.sh`
- Coverage: `/bin/bash ./scripts/coverage.sh`
- Playwright smoke: `/bin/bash ./scripts/e2e.sh`
- Deployment: `/bin/bash ./scripts/deploy.sh`
- Preview artifact: `/bin/bash ./scripts/artifact.sh preview`
- Preview launch: `/bin/bash ./scripts/preview.sh`
- Preview destroy: `/bin/bash ./scripts/destroy-preview.sh`
- Production artifact: `/bin/bash ./scripts/artifact.sh production`
