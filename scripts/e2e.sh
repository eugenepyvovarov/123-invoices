#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}"

PREVIEW_MODE=0
if [ -n "${OPENCODE_PREVIEW_PUBLIC_URL:-}" ]; then
  PREVIEW_MODE=1
fi

if [ "${PREVIEW_MODE}" = "1" ] \
  && [ -n "${OPENCODE_PLAYWRIGHT_EVIDENCE_RUNNER_IMAGE:-}" ] \
  && [ "${OPENCODE_PLAYWRIGHT_EVIDENCE_RUNNER_ACTIVE:-0}" != "1" ] \
  && [ -z "${OPENCODE_EVIDENCE_MODE:-}" ]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required to run preview Playwright evidence with OPENCODE_PLAYWRIGHT_EVIDENCE_RUNNER_IMAGE." >&2
    exit 1
  fi

  ENV_FILE="$(mktemp)"
  cleanup_evidence_runner_env() {
    rm -f "${ENV_FILE}"
  }
  trap cleanup_evidence_runner_env EXIT

  python3 - "${ENV_FILE}" <<'PY'
import os
import sys

env_file = sys.argv[1]
allowed_exact = {
    "ALLOWED_HOSTS",
    "DB_PATH",
    "DEBUG",
    "GIT_SSL_NO_VERIFY",
    "NODE_TLS_REJECT_UNAUTHORIZED",
}
allowed_prefixes = ("OPENCODE_", "PLAYWRIGHT_")

with open(env_file, "w", encoding="utf-8") as handle:
    for key, value in sorted(os.environ.items()):
        if key in allowed_exact or key.startswith(allowed_prefixes):
            if "\n" in value or "\r" in value:
                continue
            handle.write(f"{key}={value}\n")
PY

  docker run --rm \
    --env-file "${ENV_FILE}" \
    -e OPENCODE_PLAYWRIGHT_EVIDENCE_RUNNER_ACTIVE=1 \
    -v "${REPO_ROOT}:/work" \
    -w /work \
    "${OPENCODE_PLAYWRIGHT_EVIDENCE_RUNNER_IMAGE}" \
    /bin/bash ./scripts/e2e.sh "$@"
  exit $?
fi

if [ "${PREVIEW_MODE}" != "1" ] && [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

resolve_python_bin() {
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "python executable not found in PATH." >&2
  exit 1
}

resolve_playwright_port() {
  local requested_port="${PLAYWRIGHT_PORT:-}"
  local python_bin

  if [ -n "${requested_port}" ]; then
    printf '%s' "${requested_port}"
    return 0
  fi

  if [ "${PREVIEW_MODE}" = "1" ]; then
    printf '%s' "8000"
    return 0
  fi

  python_bin="$(resolve_python_bin)"
  "${python_bin}" - <<'PY'
import socket

preferred_port = 8000

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    in_use = sock.connect_ex(("127.0.0.1", preferred_port)) == 0

if in_use:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as fallback:
        fallback.bind(("127.0.0.1", 0))
        print(fallback.getsockname()[1])
else:
    print(preferred_port)
PY
}

PYTHON_BIN=""
if [ "${PREVIEW_MODE}" != "1" ]; then
  PYTHON_BIN="$(resolve_python_bin)"
  export PLAYWRIGHT_PYTHON_BIN="${PLAYWRIGHT_PYTHON_BIN:-${PYTHON_BIN}}"
fi

export PLAYWRIGHT_HOST="${PLAYWRIGHT_HOST:-127.0.0.1}"
export PLAYWRIGHT_PORT="$(resolve_playwright_port)"
if [ -n "${OPENCODE_PREVIEW_PUBLIC_URL:-}" ]; then
  export PLAYWRIGHT_BASE_URL="${PLAYWRIGHT_BASE_URL:-${OPENCODE_PREVIEW_PUBLIC_URL}}"
  export PLAYWRIGHT_SKIP_MIGRATE="${PLAYWRIGHT_SKIP_MIGRATE:-1}"
  export PLAYWRIGHT_SKIP_SEED="${PLAYWRIGHT_SKIP_SEED:-1}"
fi
export PLAYWRIGHT_BASE_URL="${PLAYWRIGHT_BASE_URL:-http://${PLAYWRIGHT_HOST}:${PLAYWRIGHT_PORT}}"
export PLAYWRIGHT_REUSE_EXISTING_SERVER="${PLAYWRIGHT_REUSE_EXISTING_SERVER:-0}"
export DEBUG="${DEBUG:-1}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}"
export DB_PATH="${DB_PATH:-db/e2e.sqlite3}"
export PLAYWRIGHT_RECOVERY_CODE_STATE_PATH="${PLAYWRIGHT_RECOVERY_CODE_STATE_PATH:-tmp/playwright-recovery-code-index.txt}"
export PLAYWRIGHT_AUTH_STATE_PATH="${PLAYWRIGHT_AUTH_STATE_PATH:-tmp/playwright-auth-state.json}"

mkdir -p "$(dirname "${DB_PATH}")"
mkdir -p "$(dirname "${PLAYWRIGHT_RECOVERY_CODE_STATE_PATH}")"
mkdir -p "$(dirname "${PLAYWRIGHT_AUTH_STATE_PATH}")"
rm -f "${PLAYWRIGHT_RECOVERY_CODE_STATE_PATH}"
rm -f "${PLAYWRIGHT_AUTH_STATE_PATH}"

if [ "${PLAYWRIGHT_PREP_ONLY:-0}" = "1" ]; then
  exit 0
fi

if [ "${PLAYWRIGHT_SKIP_NPM_CI:-0}" != "1" ]; then
  npm ci
fi

if [ "${PREVIEW_MODE}" != "1" ] \
  && [ -n "${OPENCODE_EVIDENCE_MODE:-}" ] \
  && [ "${PLAYWRIGHT_SKIP_PIP_INSTALL:-0}" != "1" ]; then
  "${PYTHON_BIN}" -m pip install --break-system-packages -r requirements.txt
fi

if [ "${PLAYWRIGHT_SKIP_MIGRATE:-0}" != "1" ]; then
  "${PYTHON_BIN}" manage.py migrate --noinput
fi

if [ "${PLAYWRIGHT_SKIP_SEED:-0}" != "1" ] && "${PYTHON_BIN}" manage.py help | "${PYTHON_BIN}" -c 'import sys; sys.exit(0 if "seed_e2e_smoke" in sys.stdin.read() else 1)'; then
  "${PYTHON_BIN}" manage.py seed_e2e_smoke
fi

exec npm exec -- playwright test "$@"
