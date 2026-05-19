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

RUNTIME_IMAGE="${OPENCODE_RUNTIME_IMAGE:-invoices-runtime:local}"
RUNTIME_TARGET="${OPENCODE_RUNTIME_TARGET:-runtime}"
HOST_PORT="${RUNTIME_SMOKE_PORT:-18000}"
CONTAINER_NAME="${RUNTIME_SMOKE_NAME:-invoices-runtime-smoke-web}"
SCHEDULER_CONTAINER_NAME="${RUNTIME_SMOKE_SCHEDULER_NAME:-invoices-runtime-smoke-scheduler}"
RUNTIME_TMPDIR="${RUNTIME_SMOKE_TMPDIR:-$(mktemp -d)}"
KEEP_RUNTIME_SMOKE_DIR="${KEEP_RUNTIME_SMOKE_DIR:-0}"

cleanup() {
  "${DOCKER_BIN}" rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  "${DOCKER_BIN}" rm -f "${SCHEDULER_CONTAINER_NAME}" >/dev/null 2>&1 || true
  if [ "${KEEP_RUNTIME_SMOKE_DIR}" != "1" ]; then
    rm -rf "${RUNTIME_TMPDIR}"
  fi
}
trap cleanup EXIT

expected_db_path="/app/db/db.sqlite3"

assert_container_db_path() {
  container_name="$1"
  actual_db_path="$("${DOCKER_BIN}" exec "${container_name}" python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings'); import django; django.setup(); from django.conf import settings; print(settings.DATABASES['default']['NAME'])")"

  if [ "${actual_db_path}" != "${expected_db_path}" ]; then
    "${DOCKER_BIN}" logs "${container_name}" >&2 || true
    printf 'runtime smoke database path mismatch for %s: expected %s, got %s\n' "${container_name}" "${expected_db_path}" "${actual_db_path}" >&2
    exit 1
  fi
}

mkdir -p "${RUNTIME_TMPDIR}/db" "${RUNTIME_TMPDIR}/media"

cd "${REPO_ROOT}"

"${DOCKER_BIN}" build --target "${RUNTIME_TARGET}" -t "${RUNTIME_IMAGE}" .

"${DOCKER_BIN}" rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
"${DOCKER_BIN}" rm -f "${SCHEDULER_CONTAINER_NAME}" >/dev/null 2>&1 || true

"${DOCKER_BIN}" run -d \
  --name "${CONTAINER_NAME}" \
  -p "${HOST_PORT}:8000" \
  -e DEBUG="0" \
  -e RUN_MIGRATIONS="1" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  -v "${RUNTIME_TMPDIR}/db:/app/db" \
  -v "${RUNTIME_TMPDIR}/media:/app/media" \
  "${RUNTIME_IMAGE}" >/dev/null

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl --fail --silent "http://127.0.0.1:${HOST_PORT}/" >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl --fail --silent "http://127.0.0.1:${HOST_PORT}/" >/dev/null; then
  "${DOCKER_BIN}" logs "${CONTAINER_NAME}" >&2 || true
  echo "runtime smoke web container failed to become ready" >&2
  exit 1
fi

assert_container_db_path "${CONTAINER_NAME}"

"${DOCKER_BIN}" run -d \
  --name "${SCHEDULER_CONTAINER_NAME}" \
  -e DEBUG="0" \
  -e RUN_MIGRATIONS="0" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  -v "${RUNTIME_TMPDIR}/db:/app/db" \
  -v "${RUNTIME_TMPDIR}/media:/app/media" \
  "${RUNTIME_IMAGE}" \
  python manage.py run_backup_scheduler --poll-interval 60 >/dev/null

sleep 2

if [ "$("${DOCKER_BIN}" inspect -f '{{.State.Running}}' "${SCHEDULER_CONTAINER_NAME}")" != "true" ]; then
  "${DOCKER_BIN}" logs "${SCHEDULER_CONTAINER_NAME}" >&2 || true
  echo "runtime smoke scheduler container failed to stay running" >&2
  exit 1
fi

assert_container_db_path "${SCHEDULER_CONTAINER_NAME}"

printf 'Runtime smoke web container is serving on http://127.0.0.1:%s\n' "${HOST_PORT}"
printf 'Runtime smoke scheduler container started with shared mounts\n'
printf 'Validated effective DB path: %s\n' "${expected_db_path}"
printf 'Mounted db dir: %s\n' "${RUNTIME_TMPDIR}/db"
printf 'Mounted media dir: %s\n' "${RUNTIME_TMPDIR}/media"
exit 0
