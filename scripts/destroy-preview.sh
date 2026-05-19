#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/preview_common.sh"

RUNTIME_DIR="$(preview_runtime_dir)"
COMPOSE_PROJECT="$(preview_compose_project)"
COMPOSE_FILE="$(preview_compose_file)"

if [ -f "${COMPOSE_FILE}" ]; then
  docker_compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" down --remove-orphans || true
fi

remove_preview_source_root
rm -rf "${RUNTIME_DIR}"
