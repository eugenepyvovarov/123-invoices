#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

resolve_docker_bin() {
  local docker_bin="${DOCKER_BIN:-}"
  if [ -z "${docker_bin}" ]; then
    docker_bin="$(command -v docker || true)"
  fi
  if [ -z "${docker_bin}" ] && [ -x /usr/local/bin/docker ]; then
    docker_bin=/usr/local/bin/docker
  fi
  if [ -z "${docker_bin}" ] && [ -x /Applications/Docker.app/Contents/Resources/bin/docker ]; then
    docker_bin=/Applications/Docker.app/Contents/Resources/bin/docker
  fi
  if [ -z "${docker_bin}" ]; then
    echo "docker executable not found in PATH or standard macOS locations." >&2
    exit 1
  fi
  printf '%s\n' "${docker_bin}"
}

DOCKER_BIN="$(resolve_docker_bin)"

docker_compose() {
  "${DOCKER_BIN}" compose "$@"
}

preview_pr_number() {
  local value="${OPENCODE_PREVIEW_PR_NUMBER:-}"
  if ! [[ "${value}" =~ ^[0-9]+$ ]]; then
    echo "OPENCODE_PREVIEW_PR_NUMBER must be set to an integer PR number." >&2
    exit 1
  fi
  printf '%s\n' "${value}"
}

preview_host() {
  local value="${OPENCODE_PREVIEW_HOST:-}"
  if [ -z "${value}" ]; then
    echo "OPENCODE_PREVIEW_HOST must be set." >&2
    exit 1
  fi
  printf '%s\n' "${value}"
}

preview_project_key() {
  local value="${OPENCODE_PREVIEW_PROJECT_KEY:-lifeisgoodlabs-invoices}"
  printf '%s\n' "${value}"
}

preview_role() {
  local value="${OPENCODE_PREVIEW_ROLE:-current}"
  case "${value}" in
    current|baseline)
      ;;
    *)
      echo "OPENCODE_PREVIEW_ROLE must be either 'current' or 'baseline'." >&2
      exit 1
      ;;
  esac
  printf '%s\n' "${value}"
}

preview_role_suffix() {
  local role
  role="$(preview_role)"
  if [ "${role}" = "current" ]; then
    return 0
  fi
  printf '%s' "-${role}"
}

preview_ref() {
  local value="${OPENCODE_PREVIEW_REF:-}"
  printf '%s\n' "${value}"
}

preview_source_worktree_dir() {
  printf '%s/source-worktree\n' "$(preview_runtime_dir)"
}

preview_source_root() {
  local ref
  ref="$(preview_ref)"
  if [ -n "${ref}" ]; then
    printf '%s\n' "$(preview_source_worktree_dir)"
    return
  fi
  printf '%s\n' "${REPO_ROOT}"
}

ensure_preview_source_root() {
  local ref
  local source_root
  ref="$(preview_ref)"
  source_root="$(preview_source_root)"
  if [ -z "${ref}" ]; then
    printf '%s\n' "${source_root}"
    return
  fi

  local resolved_ref
  if ! resolved_ref="$(git -C "${REPO_ROOT}" rev-parse --verify "${ref}^{commit}" 2>/dev/null)"; then
    echo "OPENCODE_PREVIEW_REF must resolve to a valid commit: ${ref}" >&2
    exit 1
  fi

  mkdir -p "$(dirname "${source_root}")"

  if [ -e "${source_root}" ]; then
    if git -C "${source_root}" rev-parse --git-dir >/dev/null 2>&1; then
      local current_sha
      current_sha="$(git -C "${source_root}" rev-parse HEAD)"
      if [ "${current_sha}" = "${resolved_ref}" ]; then
        printf '%s\n' "${source_root}"
        return
      fi
      git -C "${REPO_ROOT}" worktree remove --force "${source_root}" >/dev/null 2>&1 || rm -rf "${source_root}"
    else
      rm -rf "${source_root}"
    fi
  fi

  git -C "${REPO_ROOT}" worktree add --force --detach "${source_root}" "${resolved_ref}" >/dev/null
  printf '%s\n' "${source_root}"
}

remove_preview_source_root() {
  local source_root
  source_root="$(preview_source_worktree_dir)"
  if [ ! -e "${source_root}" ]; then
    return 0
  fi
  git -C "${REPO_ROOT}" worktree remove --force "${source_root}" >/dev/null 2>&1 || rm -rf "${source_root}"
}

preview_git_sha() {
  git -C "$(preview_source_root)" rev-parse --short HEAD
}

preview_image() {
  local pr_number
  local git_sha
  pr_number="$(preview_pr_number)"
  git_sha="$(preview_git_sha)"
  printf 'lifeisgoodlabs/invoices-preview:pr-%s-%s\n' "${pr_number}" "${git_sha}"
}

preview_runtime_root() {
  printf '%s\n' "${OPENCODE_PREVIEW_RUNTIME_ROOT:-${HOME}/www/03-invoices-previews}"
}

preview_runtime_dir() {
  local pr_number
  local project_key
  local role_suffix
  pr_number="$(preview_pr_number)"
  project_key="$(preview_project_key)"
  role_suffix="$(preview_role_suffix)"
  printf '%s/pr-%s%s-%s\n' "$(preview_runtime_root)" "${pr_number}" "${role_suffix}" "${project_key}"
}

preview_compose_project() {
  local pr_number
  local project_key
  local role_suffix
  pr_number="$(preview_pr_number)"
  project_key="$(preview_project_key)"
  role_suffix="$(preview_role_suffix)"
  printf 'preview-pr-%s%s-%s\n' "${pr_number}" "${role_suffix}" "${project_key}"
}

preview_port_offset() {
  local role
  role="$(preview_role)"
  case "${role}" in
    current)
      printf '0\n'
      ;;
    baseline)
      printf '1000\n'
      ;;
  esac
}

preview_port() {
  local pr_number
  local port_file
  local port_offset
  pr_number="$(preview_pr_number)"
  port_file="$(preview_runtime_dir)/preview.port"
  if [ -f "${port_file}" ]; then
    cat "${port_file}"
    return
  fi
  port_offset="$(preview_port_offset)"
  local port=$((20000 + pr_number + port_offset))
  if [ "${port}" -gt 65535 ]; then
    echo "Calculated preview port ${port} exceeds the valid TCP port range." >&2
    exit 1
  fi
  mkdir -p "$(dirname "${port_file}")"
  printf '%s\n' "${port}" > "${port_file}"
  printf '%s\n' "${port}"
}

preview_compose_file() {
  printf '%s/compose.yaml\n' "$(preview_runtime_dir)"
}

preview_env_file() {
  printf '%s/.env\n' "$(preview_runtime_dir)"
}

backend_url() {
  printf 'http://%s:%s\n' "$(preview_backend_host)" "$(preview_port)"
}

preview_backend_host() {
  printf '%s\n' "${OPENCODE_PREVIEW_BACKEND_HOST:-host.docker.internal}"
}

public_preview_url() {
  printf 'https://%s\n' "$(preview_host)"
}

health_url() {
  printf '%s/accounts/login/\n' "$(public_preview_url)"
}

wait_for_http() {
  local url="$1"
  local attempts="${2:-60}"
  local sleep_seconds="${3:-2}"
  local attempt=1
  while [ "${attempt}" -le "${attempts}" ]; do
    if curl -fsS -o /dev/null "${url}"; then
      return 0
    fi
    sleep "${sleep_seconds}"
    attempt=$((attempt + 1))
  done
  echo "Timed out waiting for ${url}" >&2
  return 1
}
