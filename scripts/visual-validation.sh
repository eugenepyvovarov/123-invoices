#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IDENTIFIER="${1:-}"

case "${IDENTIFIER}" in
  incoming-invoice-inbox)
    export OPENCODE_EVIDENCE_MODE="${OPENCODE_EVIDENCE_MODE:-visual-validation}"
    export OPENCODE_VISUAL_VALIDATION_TARGET="${OPENCODE_VISUAL_VALIDATION_TARGET:-current}"
    export PLAYWRIGHT_VIDEO="${PLAYWRIGHT_VIDEO:-retain-on-failure}"
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/incoming-invoice-inbox.spec.js --project=chromium
    ;;
  rolling-year-period-default)
    export OPENCODE_VISUAL_VALIDATION_TARGET="${OPENCODE_VISUAL_VALIDATION_TARGET:-current}"
    if [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "baseline" ] \
      && [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "current" ]; then
      echo "OPENCODE_VISUAL_VALIDATION_TARGET must be baseline or current." >&2
      exit 2
    fi
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/rolling-year-period.spec.js --project=chromium
    ;;
  customer-payment-notes-billing-defaults)
    export OPENCODE_VISUAL_VALIDATION_TARGET="${OPENCODE_VISUAL_VALIDATION_TARGET:-current}"
    export OPENCODE_VISUAL_VALIDATION_IDENTIFIER="${IDENTIFIER}"
    if [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "baseline" ] \
      && [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "current" ]; then
      echo "OPENCODE_VISUAL_VALIDATION_TARGET must be baseline or current." >&2
      exit 2
    fi
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/customer-payment-notes.spec.js --project=chromium
    ;;
  bulk-toolbar-spacing)
    export OPENCODE_VISUAL_VALIDATION_TARGET="${OPENCODE_VISUAL_VALIDATION_TARGET:-current}"
    export OPENCODE_VISUAL_VALIDATION_IDENTIFIER="${IDENTIFIER}"
    if [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "baseline" ] \
      && [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "current" ]; then
      echo "OPENCODE_VISUAL_VALIDATION_TARGET must be baseline or current." >&2
      exit 2
    fi
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/bulk-toolbar-spacing.spec.js --project=chromium
    ;;
  "")
    echo "Usage: ./scripts/visual-validation.sh {incoming-invoice-inbox|rolling-year-period-default|customer-payment-notes-billing-defaults|bulk-toolbar-spacing}" >&2
    exit 2
    ;;
  *)
    echo "Unknown visual validation identifier: ${IDENTIFIER}" >&2
    exit 2
    ;;
esac
