#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENARIO="${1:-}"

case "${SCENARIO}" in
  rolling-year-period-default)
    export PLAYWRIGHT_VIDEO="${PLAYWRIGHT_VIDEO:-on}"
    export OPENCODE_DEMO_SCENARIO="${SCENARIO}"
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/rolling-year-period.spec.js --project=chromium
    ;;
  "")
    echo "Usage: ./scripts/demo-evidence.sh rolling-year-period-default" >&2
    exit 2
    ;;
  *)
    echo "Unknown demo evidence scenario: ${SCENARIO}" >&2
    exit 2
    ;;
esac
