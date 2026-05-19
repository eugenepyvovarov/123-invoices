#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-preview}"
if [ $# -gt 0 ]; then
  shift
fi

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

resolve_registry_user_from_token() {
  GITEA_SERVER_URL="${GITEA_SERVER_URL}" GITEA_TOKEN="${GITEA_TOKEN}" python3 - <<'PY'
import json
import os
import sys
import urllib.request

base_url = os.environ["GITEA_SERVER_URL"].rstrip("/")
token = os.environ["GITEA_TOKEN"].strip()
request = urllib.request.Request(
    f"{base_url}/api/v1/user",
    headers={"Authorization": f"token {token}", "Accept": "application/json"},
)
with urllib.request.urlopen(request, timeout=20) as response:
    payload = json.load(response)
login = str(payload.get("login") or "").strip()
if not login:
    raise SystemExit("Unable to resolve Gitea login from token.")
sys.stdout.write(login)
PY
}

login_registry_if_needed() {
  local registry_host="${1}"
  local registry_user=""
  local registry_password=""

  if [ -n "${REGISTRY_PASSWORD:-}" ]; then
    registry_user="${REGISTRY_USER:-}"
    registry_password="${REGISTRY_PASSWORD}"
    if [ -z "${registry_user}" ]; then
      echo "REGISTRY_USER must be set when REGISTRY_PASSWORD is provided." >&2
      exit 1
    fi
  elif [ -n "${GITEA_TOKEN:-}" ]; then
    registry_user="${REGISTRY_USER:-${GITEA_REGISTRY_USER:-}}"
    if [ -z "${registry_user}" ]; then
      registry_user="$(resolve_registry_user_from_token)"
    fi
    registry_password="${GITEA_TOKEN}"
  else
    echo "No registry credentials provided; assuming an existing docker login for ${registry_host}." >&2
    return 0
  fi

  printf '%s' "${registry_password}" | "${DOCKER_BIN}" login "${registry_host}" -u "${registry_user}" --password-stdin >&2
}

run_preview_artifact() {
  local script_dir image_tag
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # shellcheck disable=SC1091
  source "${script_dir}/preview_common.sh"

  SOURCE_ROOT="$(ensure_preview_source_root)"
  cd "${SOURCE_ROOT}"

  image_tag="$(preview_image)"

  echo "Building preview image ${image_tag}" >&2
  "${DOCKER_BIN}" build --target runtime -t "${image_tag}" .
}

run_production_artifact() {
  local registry_host registry_image image tag sha_tag_default sha_tag
  cd "${REPO_ROOT}"

  registry_host="${REGISTRY_HOST:-git.ultramac.work}"
  registry_image="${REGISTRY_IMAGE:-${registry_host}/lifeisgoodlabs/invoices}"
  image="${IMAGE:-${registry_image}}"
  tag="${TAG:-latest}"
  sha_tag_default="$(git rev-parse --short HEAD 2>/dev/null || true)"
  sha_tag="${SHA_TAG:-$sha_tag_default}"
  GITEA_SERVER_URL="${GITEA_SERVER_URL:-https://${registry_host}}"
  export GITEA_SERVER_URL

  login_registry_if_needed "${registry_host}"

  IMAGE="${image}" TAG="${tag}" SHA_TAG="${sha_tag}" "${REPO_ROOT}/scripts/build_and_push.sh" >&2

  IMAGE="${image}" TAG="${tag}" SHA_TAG="${sha_tag}" python3 - <<'PY'
import json
import os

image = os.environ["IMAGE"].strip()
tag = os.environ["TAG"].strip()
sha_tag = os.environ["SHA_TAG"].strip()
published_artifacts = [
    {
        "name": "container-image-latest",
        "type": "docker-image",
        "reference": f"{image}:{tag}",
    }
]
if sha_tag and sha_tag != tag:
    published_artifacts.append(
        {
            "name": "container-image-sha",
            "type": "docker-image",
            "reference": f"{image}:{sha_tag}",
        }
    )

summary = f"Published {image}:{tag}"
if sha_tag and sha_tag != tag:
    summary += f" and {image}:{sha_tag}"

print(json.dumps({"published_artifacts": published_artifacts, "summary": summary}))
PY
}

DOCKER_BIN="$(resolve_docker_bin)"

case "${MODE}" in
  preview)
    run_preview_artifact "$@"
    ;;
  production)
    run_production_artifact "$@"
    ;;
  *)
    echo "Usage: ./scripts/artifact.sh [preview|production]" >&2
    exit 1
    ;;
esac
