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
RUNTIME_IMAGE="${OPENCODE_RUNTIME_IMAGE:-invoices-runtime:local}"
RUNTIME_TARGET="${OPENCODE_RUNTIME_TARGET:-runtime}"

cd "${REPO_ROOT}"

"${DOCKER_BIN}" build --target "${TEST_TARGET}" -t "${TEST_IMAGE}" .

"${DOCKER_BIN}" run --rm \
  -e DEBUG="${DEBUG:-1}" \
  -e DB_PATH="${DB_PATH:-/tmp/db.sqlite3}" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  -e PYTHONMALLOC="${PYTHONMALLOC:-malloc}" \
  "${TEST_IMAGE}" \
  python manage.py test

runtime_tmpdir="$(mktemp -d)"
runtime_name_suffix="${OPENCODE_CI_CONTAINER_SUFFIX:-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}-${GITHUB_JOB:-job}-$$-${RANDOM}}"
runtime_name_suffix="${runtime_name_suffix//[^A-Za-z0-9_.-]/-}"
web_container_name="invoices-runtime-web-ci-${runtime_name_suffix}"
scheduler_container_name="invoices-runtime-scheduler-ci-${runtime_name_suffix}"
mcp_container_name="invoices-runtime-mcp-ci-${runtime_name_suffix}"
make_probe_bearer() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c "import uuid; print(uuid.uuid4().hex + uuid.uuid4().hex)"
  fi
}
mcp_api_bearer="$(make_probe_bearer)"
mcp_client_bearer="$(make_probe_bearer)"
cleanup() {
  "${DOCKER_BIN}" rm -f "${web_container_name}" >/dev/null 2>&1 || true
  "${DOCKER_BIN}" rm -f "${scheduler_container_name}" >/dev/null 2>&1 || true
  "${DOCKER_BIN}" rm -f "${mcp_container_name}" >/dev/null 2>&1 || true
  rm -rf "${runtime_tmpdir}"
}
trap cleanup EXIT
mkdir -p "${runtime_tmpdir}/db" "${runtime_tmpdir}/media"

"${DOCKER_BIN}" build --target "${RUNTIME_TARGET}" -t "${RUNTIME_IMAGE}" .

"${DOCKER_BIN}" run --rm \
  -e DEBUG="0" \
  -e RUN_MIGRATIONS="1" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  -v "${runtime_tmpdir}/db:/app/db" \
  -v "${runtime_tmpdir}/media:/app/media" \
  "${RUNTIME_IMAGE}" \
  python -c "from pathlib import Path; Path('/app/db/entrypoint-smoke.txt').write_text('ok'); Path('/app/media/entrypoint-smoke.txt').write_text('ok')"

"${DOCKER_BIN}" run -d \
  --name "${web_container_name}" \
  -e DEBUG="0" \
  -e RUN_MIGRATIONS="1" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  -v "${runtime_tmpdir}/db:/app/db" \
  -v "${runtime_tmpdir}/media:/app/media" \
  "${RUNTIME_IMAGE}" >/dev/null

"${DOCKER_BIN}" run -d \
  --name "${scheduler_container_name}" \
  -e DEBUG="0" \
  -e RUN_MIGRATIONS="0" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  -v "${runtime_tmpdir}/db:/app/db" \
  -v "${runtime_tmpdir}/media:/app/media" \
  "${RUNTIME_IMAGE}" \
  python manage.py run_backup_scheduler --poll-interval 60 >/dev/null

"${DOCKER_BIN}" run -d \
  --name "${mcp_container_name}" \
  -e DEBUG="0" \
  -e RUN_MIGRATIONS="0" \
  -e ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}" \
  -e INVOICES_MCP_API_BASE_URL="http://127.0.0.1:8000/api/" \
  -e INVOICES_MCP_API_TOKEN="${mcp_api_bearer}" \
  -e INVOICES_MCP_CLIENT_TOKENS="${mcp_client_bearer}" \
  -e INVOICES_MCP_HOST="0.0.0.0" \
  -e INVOICES_MCP_PORT="8765" \
  -v "${runtime_tmpdir}/db:/app/db" \
  -v "${runtime_tmpdir}/media:/app/media" \
  "${RUNTIME_IMAGE}" \
  python -m invoices_mcp.server >/dev/null

sleep 2

if [ "$("${DOCKER_BIN}" inspect -f '{{.State.Running}}' "${web_container_name}")" != "true" ]; then
  "${DOCKER_BIN}" logs "${web_container_name}" >&2 || true
  echo "runtime smoke web container failed to stay running" >&2
  exit 1
fi

web_db_path="$("${DOCKER_BIN}" exec "${web_container_name}" python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings'); import django; django.setup(); from django.conf import settings; print(settings.DATABASES['default']['NAME'])")"

if [ "${web_db_path}" != "/app/db/db.sqlite3" ]; then
  "${DOCKER_BIN}" logs "${web_container_name}" >&2 || true
  printf 'runtime smoke database path mismatch for web: expected %s, got %s\n' "/app/db/db.sqlite3" "${web_db_path}" >&2
  exit 1
fi

if [ "$("${DOCKER_BIN}" inspect -f '{{.State.Running}}' "${scheduler_container_name}")" != "true" ]; then
  "${DOCKER_BIN}" logs "${scheduler_container_name}" >&2 || true
  echo "runtime smoke scheduler container failed to stay running" >&2
  exit 1
fi

if [ "$("${DOCKER_BIN}" inspect -f '{{.State.Running}}' "${mcp_container_name}")" != "true" ]; then
  "${DOCKER_BIN}" logs "${mcp_container_name}" >&2 || true
  echo "runtime smoke MCP container failed to stay running" >&2
  exit 1
fi

mcp_probe_passed=0
for _ in 1 2 3 4 5; do
  if "${DOCKER_BIN}" exec "${mcp_container_name}" python scripts/mcp_probe.py --url "http://127.0.0.1:8765/mcp/" --token "${mcp_client_bearer}"; then
    mcp_probe_passed=1
    break
  fi
  sleep 1
done

if [ "${mcp_probe_passed}" != "1" ]; then
  "${DOCKER_BIN}" logs "${mcp_container_name}" >&2 || true
  echo "runtime smoke MCP probe failed" >&2
  exit 1
fi

scheduler_db_path="$("${DOCKER_BIN}" exec "${scheduler_container_name}" python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings'); import django; django.setup(); from django.conf import settings; print(settings.DATABASES['default']['NAME'])")"

if [ "${scheduler_db_path}" != "/app/db/db.sqlite3" ]; then
  "${DOCKER_BIN}" logs "${scheduler_container_name}" >&2 || true
  printf 'runtime smoke database path mismatch for scheduler: expected %s, got %s\n' "/app/db/db.sqlite3" "${scheduler_db_path}" >&2
  exit 1
fi
