#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:-}"
if [ "${SCENARIO}" != "incoming-invoice-review-conversion" ]; then
  echo "Usage: $0 incoming-invoice-review-conversion" >&2
  exit 2
fi

export OPENCODE_EVIDENCE_MODE="${OPENCODE_EVIDENCE_MODE:-demo}"
export PLAYWRIGHT_VIDEO="${PLAYWRIGHT_VIDEO:-on}"

exec /bin/bash ./scripts/e2e.sh tests/e2e/incoming-invoice-inbox.spec.js --project=chromium
