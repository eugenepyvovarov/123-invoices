#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}"

DOCKER_BIN="${DOCKER_BIN:-docker}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-03-invoices}"
RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE:-${REPO_ROOT}/.env}"
WEB_VERIFY_URL="${WEB_VERIFY_URL:-http://127.0.0.1:8000/}"
WEB_VERIFY_ATTEMPTS="${WEB_VERIFY_ATTEMPTS:-10}"
WEB_VERIFY_DELAY_SECONDS="${WEB_VERIFY_DELAY_SECONDS:-3}"
SCHEDULER_LOG_TAIL_LINES="${SCHEDULER_LOG_TAIL_LINES:-50}"
EXPECTED_SERVICES=(web scheduler mcp)

runtime_env_value() {
  local key="$1"

  if [ ! -f "${RUNTIME_ENV_FILE}" ]; then
    return 0
  fi

  awk -v key="${key}" '
    $0 ~ "^[[:space:]]*(#|$)" { next }
    index($0, key "=") == 1 {
      value = substr($0, length(key) + 2)
      if (value ~ /^".*"$/ || value ~ /^'"'"'.*'"'"'$/) {
        value = substr(value, 2, length(value) - 2)
      }
      print value
      exit
    }
  ' "${RUNTIME_ENV_FILE}"
}

resolve_web_verify_host() {
  local resolved_host="${WEB_VERIFY_HOST:-${RENDER_EXTERNAL_HOSTNAME:-}}"

  if [ -z "${resolved_host}" ]; then
    resolved_host="$(runtime_env_value RENDER_EXTERNAL_HOSTNAME)"
  fi

  if [ -z "${resolved_host}" ]; then
    echo "Web verification host is not configured; set WEB_VERIFY_HOST, RENDER_EXTERNAL_HOSTNAME, or RENDER_EXTERNAL_HOSTNAME in '${RUNTIME_ENV_FILE}'." >&2
    exit 1
  fi

  printf '%s\n' "${resolved_host}"
}

verify_service_container() {
  local service="$1"
  local container_id
  local project_label
  local container_name
  local expected_name
  local state
  local restart_count

  container_id="$(${DOCKER_BIN} compose ps -q "${service}")"
  if [ -z "${container_id}" ]; then
    echo "No container found for service '${service}' in stack '${COMPOSE_PROJECT_NAME}'." >&2
    exit 1
  fi

  project_label="$(${DOCKER_BIN} inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "${container_id}")"
  if [ "${project_label}" != "${COMPOSE_PROJECT_NAME}" ]; then
    echo "Service '${service}' is not running under compose project '${COMPOSE_PROJECT_NAME}'." >&2
    exit 1
  fi

  container_name="$(${DOCKER_BIN} inspect -f '{{ .Name }}' "${container_id}")"
  container_name="${container_name#/}"
  expected_name="${COMPOSE_PROJECT_NAME}-${service}-1"
  if [ "${container_name}" != "${expected_name}" ]; then
    echo "Expected container '${expected_name}' for service '${service}', found '${container_name}'." >&2
    exit 1
  fi

  state="$(${DOCKER_BIN} inspect -f '{{ .State.Status }}' "${container_id}")"
  if [ "${state}" != "running" ]; then
    echo "Service '${service}' is not running (state: ${state})." >&2
    exit 1
  fi

  restart_count="$(${DOCKER_BIN} inspect -f '{{ .RestartCount }}' "${container_id}")"
  if [ "${restart_count}" != "0" ]; then
    echo "Service '${service}' restarted ${restart_count} times after rollout." >&2
    exit 1
  fi
}

verify_scheduler_started_cleanly() {
  local scheduler_logs

  scheduler_logs="$(${DOCKER_BIN} compose logs --no-color --tail "${SCHEDULER_LOG_TAIL_LINES}" scheduler)"

  if printf '%s\n' "${scheduler_logs}" | grep -Fq 'Traceback (most recent call last):'; then
    echo "Scheduler logs contain a Python traceback after rollout." >&2
    exit 1
  fi

  if printf '%s\n' "${scheduler_logs}" | grep -Fq 'Backup scheduler run failed:'; then
    echo "Scheduler logs show a startup failure after rollout." >&2
    exit 1
  fi
}

first_csv_value() {
  local csv_value="$1"
  local first_value

  IFS=',' read -r first_value _ <<< "${csv_value}"
  first_value="${first_value#"${first_value%%[![:space:]]*}"}"
  first_value="${first_value%"${first_value##*[![:space:]]}"}"
  printf '%s\n' "${first_value}"
}

normalize_mcp_path() {
  local path="$1"
  path="/${path#/}"
  if [ "${path%/}" = "${path}" ]; then
    path="${path}/"
  fi
  printf '%s\n' "${path}"
}

verify_mcp_protocol() {
  local token_csv
  local token
  local mcp_port
  local mcp_path
  local mcp_url

  token_csv="${INVOICES_MCP_AUTH_TEST_TOKENS:-$(runtime_env_value INVOICES_MCP_AUTH_TEST_TOKENS)}"
  token="$(first_csv_value "${token_csv}")"
  if [ -z "${token}" ]; then
    echo "INVOICES_MCP_AUTH_TEST_TOKENS is required to verify authenticated MCP tool discovery before OAuth probe credentials exist." >&2
    exit 1
  fi

  mcp_port="${INVOICES_MCP_PORT:-$(runtime_env_value INVOICES_MCP_PORT)}"
  mcp_port="${mcp_port:-8765}"
  mcp_path="${INVOICES_MCP_ENDPOINT_PATH:-$(runtime_env_value INVOICES_MCP_ENDPOINT_PATH)}"
  mcp_path="$(normalize_mcp_path "${mcp_path:-/mcp/}")"
  mcp_url="http://127.0.0.1:${mcp_port}${mcp_path}"

  ${DOCKER_BIN} compose exec -T mcp python scripts/mcp_probe.py --url "${mcp_url}" --token "${token}"
}

for service in "${EXPECTED_SERVICES[@]}"; do
  running_service="$(${DOCKER_BIN} compose ps --services --status running "${service}")"
  if [ "${running_service}" != "${service}" ]; then
    echo "Service '${service}' is not listed as running in stack '${COMPOSE_PROJECT_NAME}'." >&2
    exit 1
  fi
  verify_service_container "${service}"
done

verify_scheduler_started_cleanly
verify_mcp_protocol

WEB_VERIFY_HOST="$(resolve_web_verify_host)"

for attempt in $(seq 1 "${WEB_VERIFY_ATTEMPTS}"); do
  if "${PYTHON_BIN}" - "${WEB_VERIFY_URL}" "${WEB_VERIFY_HOST}" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
host = sys.argv[2]
request = urllib.request.Request(url, headers={"Host": host})

try:
    with urllib.request.urlopen(request, timeout=10) as response:
        sys.exit(0 if 200 <= response.status < 400 else 1)
except urllib.error.HTTPError as exc:
    sys.exit(1)
except Exception:
    sys.exit(1)
PY
  then
    exit 0
  fi

  if [ "${attempt}" -eq "${WEB_VERIFY_ATTEMPTS}" ]; then
    echo "Web verification failed for '${WEB_VERIFY_URL}' with Host '${WEB_VERIFY_HOST}' after ${WEB_VERIFY_ATTEMPTS} attempts." >&2
    exit 1
  fi

  sleep "${WEB_VERIFY_DELAY_SECONDS}"
done
