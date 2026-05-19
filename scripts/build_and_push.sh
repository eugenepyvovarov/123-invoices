#!/usr/bin/env bash
set -euo pipefail

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

# Build and push a multi-arch image to the Gitea registry.
# Usage:
#   IMAGE=git.ultramac.work/lifeisgoodlabs/invoices TAG=latest ./scripts/build_and_push.sh
# Optional:
#   PLATFORMS=linux/amd64,linux/arm64   # override platforms
#   TAG=latest                          # main tag
#   SHA_TAG=                            # set to add a second tag (defaults to git short SHA if available)

IMAGE="${IMAGE:-git.ultramac.work/lifeisgoodlabs/invoices}"
TAG="${TAG:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
SHA_TAG_DEFAULT="$(git rev-parse --short HEAD 2>/dev/null || true)"
SHA_TAG="${SHA_TAG:-$SHA_TAG_DEFAULT}"

BUILD_TAGS=( -t "${IMAGE}:${TAG}" )
if [ -n "${SHA_TAG}" ] && [ "${SHA_TAG}" != "${TAG}" ]; then
  BUILD_TAGS+=( -t "${IMAGE}:${SHA_TAG}" )
fi

echo "Building ${IMAGE} for platforms: ${PLATFORMS} with tags: ${BUILD_TAGS[*]#-t }"
"${DOCKER_BIN}" buildx build --platform "${PLATFORMS}" "${BUILD_TAGS[@]}" --push .
