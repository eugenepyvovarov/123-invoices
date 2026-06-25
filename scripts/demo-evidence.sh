#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENARIO="${1:-}"

case "${SCENARIO}" in
  incoming-invoice-review-conversion)
    export OPENCODE_EVIDENCE_MODE="${OPENCODE_EVIDENCE_MODE:-demo}"
    export PLAYWRIGHT_VIDEO="${PLAYWRIGHT_VIDEO:-on}"
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/incoming-invoice-inbox.spec.js --project=chromium
    ;;
  rolling-year-period-default)
    export PLAYWRIGHT_VIDEO="${PLAYWRIGHT_VIDEO:-on}"
    export OPENCODE_DEMO_SCENARIO="${SCENARIO}"
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/rolling-year-period.spec.js --project=chromium
    ;;
  customer-payment-notes-override)
    export PLAYWRIGHT_VIDEO="${PLAYWRIGHT_VIDEO:-on}"
    export OPENCODE_DEMO_SCENARIO="${SCENARIO}"
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/customer-payment-notes.spec.js --project=chromium
    ;;
  "")
    echo "Usage: ./scripts/demo-evidence.sh {incoming-invoice-review-conversion|rolling-year-period-default|customer-payment-notes-override}" >&2
    exit 2
    ;;
  *)
    echo "Unknown demo evidence scenario: ${SCENARIO}" >&2
    exit 2
    ;;
esac
