#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_BIN="${DOCKER_BIN:-}"
if [ -z "${DOCKER_BIN}" ]; then
  DOCKER_BIN="$(command -v docker || true)"
fi
if [ -z "${DOCKER_BIN}" ] && [ -x /usr/local/bin/docker ]; then
  DOCKER_BIN=/usr/local/bin/docker
fi
if [ -z "${DOCKER_BIN}" ] && [ -x /Applications/Docker.app/Contents/Resources/bin/docker ]; then
  DOCKER_BIN=/Applications/Docker.app/Contents/Resources/bin/docker
fi
if [ -z "${DOCKER_BIN}" ]; then
  echo "docker executable not found in PATH or standard macOS locations." >&2
  exit 1
fi

TEST_IMAGE="${OPENCODE_TEST_IMAGE:-invoices-test:local}"
TEST_TARGET="${OPENCODE_TEST_TARGET:-test}"

cd "${REPO_ROOT}"

"${DOCKER_BIN}" build --target "${TEST_TARGET}" -t "${TEST_IMAGE}" .

exec "${DOCKER_BIN}" run --rm \
  -e SECRET_KEY="${SECRET_KEY:-opencode-ci-secret}" \
  -e DEBUG="${DEBUG:-1}" \
  -e DB_PATH="${DB_PATH:-/tmp/db.sqlite3}" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  "${TEST_IMAGE}" \
  sh -lc 'python -m coverage erase && python -m coverage run manage.py test && python -m coverage report -m'
