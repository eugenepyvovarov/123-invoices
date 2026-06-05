#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IDENTIFIER="${1:-}"

case "${IDENTIFIER}" in
  rolling-year-period-default)
    export OPENCODE_VISUAL_VALIDATION_TARGET="${OPENCODE_VISUAL_VALIDATION_TARGET:-current}"
    if [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "baseline" ] \
      && [ "${OPENCODE_VISUAL_VALIDATION_TARGET}" != "current" ]; then
      echo "OPENCODE_VISUAL_VALIDATION_TARGET must be baseline or current." >&2
      exit 2
    fi
    exec /bin/bash "${REPO_ROOT}/scripts/e2e.sh" tests/e2e/rolling-year-period.spec.js --project=chromium
    ;;
  "")
    echo "Usage: ./scripts/visual-validation.sh rolling-year-period-default" >&2
    exit 2
    ;;
  *)
    echo "Unknown visual validation identifier: ${IDENTIFIER}" >&2
    exit 2
    ;;
esac
