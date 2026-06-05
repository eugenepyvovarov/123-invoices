#!/usr/bin/env bash
set -euo pipefail

IDENTIFIER="${1:-}"
if [ "${IDENTIFIER}" != "incoming-invoice-inbox" ]; then
  echo "Usage: $0 incoming-invoice-inbox" >&2
  exit 2
fi

export OPENCODE_EVIDENCE_MODE="${OPENCODE_EVIDENCE_MODE:-visual-validation}"
export OPENCODE_VISUAL_VALIDATION_TARGET="${OPENCODE_VISUAL_VALIDATION_TARGET:-current}"
export PLAYWRIGHT_VIDEO="${PLAYWRIGHT_VIDEO:-retain-on-failure}"

exec /bin/bash ./scripts/e2e.sh tests/e2e/incoming-invoice-inbox.spec.js --project=chromium
