#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-${REPO_ROOT}/.deploy.env}"
RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE:-${REPO_ROOT}/.env}"

cd "${REPO_ROOT}"

if [ -f "${DEPLOY_ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${DEPLOY_ENV_FILE}"
  set +a
fi

PHASE_BIN="${PHASE_BIN:-}"
if [ -z "${PHASE_BIN}" ]; then
  PHASE_BIN="$(command -v phase || true)"
fi
export PHASE_APP="${PHASE_APP:-lifeisgoodlabs-invoices}"
export PHASE_ENV="${PHASE_ENV:-Development}"

load_phase_deploy_secrets() {
  if [ -z "${PHASE_BIN}" ]; then
    return 0
  fi

  local missing_keys=()
  local key
  for key in SECRET_KEY RENDER_EXTERNAL_HOSTNAME REGISTRY_USER REGISTRY_PASSWORD; do
    if [ -z "${!key:-}" ]; then
      missing_keys+=("${key}")
    fi
  done

  if [ "${#missing_keys[@]}" -eq 0 ]; then
    return 0
  fi

  local phase_env_file
  phase_env_file="$(mktemp)"

  if ! "${PHASE_BIN}" secrets export "${missing_keys[@]}" --app "${PHASE_APP}" --env "${PHASE_ENV}" --format dotenv > "${phase_env_file}"; then
    rm -f "${phase_env_file}"
    echo "Failed to load deploy secrets from Phase app '${PHASE_APP}' env '${PHASE_ENV}'." >&2
    exit 1
  fi

  set -a
  # shellcheck disable=SC1090
  source "${phase_env_file}"
  set +a
  rm -f "${phase_env_file}"
}

normalize_csv_values() {
  local csv_value="$1"
  shift

  local raw_values=()
  local raw_value
  local normalized_value
  local required_value
  local normalized_csv=""

  append_normalized_value() {
    local value="$1"
    case ",${normalized_csv}," in
      *",${value},"*) ;;
      *)
        if [ -n "${normalized_csv}" ]; then
          normalized_csv="${normalized_csv},${value}"
        else
          normalized_csv="${value}"
        fi
        ;;
    esac
  }

  if [ -n "${csv_value}" ]; then
    IFS=',' read -r -a raw_values <<< "${csv_value}"
    for raw_value in "${raw_values[@]}"; do
      normalized_value="${raw_value#"${raw_value%%[![:space:]]*}"}"
      normalized_value="${normalized_value%"${normalized_value##*[![:space:]]}"}"
      if [ -n "${normalized_value}" ]; then
        append_normalized_value "${normalized_value}"
      fi
    done
  fi

  for required_value in "$@"; do
    append_normalized_value "${required_value}"
  done

  printf '%s\n' "${normalized_csv}"
}

require_managed_runtime_inputs() {
  local missing_keys=()
  local key

  for key in SECRET_KEY RENDER_EXTERNAL_HOSTNAME; do
    if [ -z "${!key:-}" ]; then
      missing_keys+=("${key}")
    fi
  done

  if [ "${#missing_keys[@]}" -gt 0 ]; then
    echo "Missing required deploy-managed runtime env: ${missing_keys[*]}." >&2
    echo "Set the missing keys in the shell/.deploy.env or make them available via Phase app '${PHASE_APP}' env '${PHASE_ENV}'." >&2
    exit 1
  fi
}

normalize_managed_runtime_host_env() {
  require_managed_runtime_inputs

  export RENDER_EXTERNAL_HOSTNAME
  export ALLOWED_HOSTS
  export CSRF_TRUSTED_ORIGINS

  ALLOWED_HOSTS="$(normalize_csv_values "${ALLOWED_HOSTS:-}" "127.0.0.1" "localhost" "${RENDER_EXTERNAL_HOSTNAME}")"
  CSRF_TRUSTED_ORIGINS="$(normalize_csv_values "${CSRF_TRUSTED_ORIGINS:-}" "https://${RENDER_EXTERNAL_HOSTNAME}")"
}

sync_managed_runtime_env() {
  local runtime_env_dir
  runtime_env_dir="$(dirname "${RUNTIME_ENV_FILE}")"
  mkdir -p "${runtime_env_dir}"

  local temp_env_file
  temp_env_file="$(mktemp "${runtime_env_dir}/.env.tmp.XXXXXX")"

  local managed_keys_regex
  managed_keys_regex='^(SECRET_KEY|RENDER_EXTERNAL_HOSTNAME|ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS)='

  if [ -f "${RUNTIME_ENV_FILE}" ]; then
    if ! awk -v managed_keys_regex="${managed_keys_regex}" '
      $0 ~ managed_keys_regex { next }
      { print }
    ' "${RUNTIME_ENV_FILE}" > "${temp_env_file}"; then
      rm -f "${temp_env_file}"
      echo "Failed to read existing runtime env file '${RUNTIME_ENV_FILE}'." >&2
      exit 1
    fi
  fi

  {
    printf 'SECRET_KEY=%s\n' "${SECRET_KEY}"
    printf 'RENDER_EXTERNAL_HOSTNAME=%s\n' "${RENDER_EXTERNAL_HOSTNAME}"
    printf 'ALLOWED_HOSTS=%s\n' "${ALLOWED_HOSTS}"
    printf 'CSRF_TRUSTED_ORIGINS=%s\n' "${CSRF_TRUSTED_ORIGINS}"
  } >> "${temp_env_file}"

  mv "${temp_env_file}" "${RUNTIME_ENV_FILE}"
}

load_phase_deploy_secrets
normalize_managed_runtime_host_env
sync_managed_runtime_env

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

export REGISTRY_HOST="${REGISTRY_HOST:-git.ultramac.work}"
export REGISTRY_IMAGE="${REGISTRY_IMAGE:-${REGISTRY_HOST}/lifeisgoodlabs/invoices}"
export IMAGE="${IMAGE:-${REGISTRY_IMAGE}}"
export TAG="${TAG:-latest}"
export SHA_TAG="${SHA_TAG:-$(git rev-parse --short HEAD)}"
export ROLLOUT_IMAGE_TAG="${ROLLOUT_IMAGE_TAG:-${SHA_TAG}}"
export INVOICES_IMAGE="${INVOICES_IMAGE:-${IMAGE}:${ROLLOUT_IMAGE_TAG}}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-03-invoices}"

if [ -n "${REGISTRY_PASSWORD:-}" ]; then
  if [ -z "${REGISTRY_USER:-}" ]; then
    echo "REGISTRY_USER must be set when REGISTRY_PASSWORD is provided." >&2
    exit 1
  fi
  printf '%s' "${REGISTRY_PASSWORD}" | "${DOCKER_BIN}" login "${REGISTRY_HOST}" -u "${REGISTRY_USER}" --password-stdin
fi

"${REPO_ROOT}/scripts/build_and_push.sh"

"${DOCKER_BIN}" compose pull web scheduler mcp
"${DOCKER_BIN}" compose up -d web
"${DOCKER_BIN}" compose up -d scheduler
"${DOCKER_BIN}" compose up -d mcp
"${REPO_ROOT}/scripts/verify_deploy.sh"
