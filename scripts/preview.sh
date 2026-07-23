#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/preview_common.sh"

SOURCE_ROOT="$(ensure_preview_source_root)"
cd "${SOURCE_ROOT}"

PREVIEW_HOST="$(preview_host)"
PREVIEW_PORT="$(preview_port)"
PREVIEW_BACKEND_HOST="$(preview_backend_host)"
RUNTIME_DIR="$(preview_runtime_dir)"
COMPOSE_PROJECT="$(preview_compose_project)"
COMPOSE_FILE="$(preview_compose_file)"
ENV_FILE="$(preview_env_file)"
IMAGE_TAG="$(preview_image)"

mkdir -p "${RUNTIME_DIR}"

cat > "${ENV_FILE}" <<EOF
SECRET_KEY=preview-pr-$(preview_pr_number)-$(preview_git_sha)
DEBUG=1
DB_PATH=/app/db/db.sqlite3
MEDIA_ROOT=/app/media
RENDER_EXTERNAL_HOSTNAME=${PREVIEW_HOST}
ALLOWED_HOSTS=127.0.0.1,localhost,${PREVIEW_HOST},${PREVIEW_BACKEND_HOST},.preview.ultramac.work
CSRF_TRUSTED_ORIGINS=https://${PREVIEW_HOST}
SENTRY_DSN=
EOF

cat > "${COMPOSE_FILE}" <<EOF
services:
  web:
    image: ${IMAGE_TAG}
    env_file:
      - ${ENV_FILE}
    environment:
      DEBUG: "1"
      BACKUP_EXECUTION_LOCK_PATH: /app/media/.locks/backup-execution.lock
      RUN_MIGRATIONS: "1"
    command: gunicorn app.wsgi:application --bind 0.0.0.0:8000
    restart: unless-stopped
    volumes:
      - preview_db:/app/db
      - preview_media:/app/media
      - ${ENV_FILE}:/app/.env:ro
    ports:
      - "${PREVIEW_PORT}:8000"

  scheduler:
    image: ${IMAGE_TAG}
    env_file:
      - ${ENV_FILE}
    environment:
      DEBUG: "1"
      BACKUP_EXECUTION_LOCK_PATH: /app/media/.locks/backup-execution.lock
      RUN_MIGRATIONS: "0"
    command: python manage.py run_backup_scheduler
    restart: unless-stopped
    depends_on:
      - web
    volumes:
      - preview_db:/app/db
      - preview_media:/app/media
      - ${ENV_FILE}:/app/.env:ro

volumes:
  preview_db:
  preview_media:
EOF

docker_compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" up -d --force-recreate web >&2
if ! wait_for_http "http://127.0.0.1:${PREVIEW_PORT}/accounts/login/" 120 2; then
  docker_compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" ps >&2 || true
  docker_compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" logs --no-color --tail=200 web >&2 || true
  exit 1
fi

docker_compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" exec -T web python manage.py seed_e2e_smoke >&2
docker_compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" exec -T web python manage.py shell -c "from django.contrib.auth import get_user_model; from accounts.utils import otp as otp_utils; User = get_user_model(); user = User.objects.get(email='e2e-smoke@example.com'); otp_utils.disable_two_factor(user); user.is_staff = True; user.is_superuser = True; user.save(update_fields=['is_staff', 'is_superuser'])" >&2

docker_compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" up -d --force-recreate scheduler >&2

export OPENCODE_PREVIEW_RESULT_BACKEND_URL="$(backend_url)"
export OPENCODE_PREVIEW_RESULT_HEALTH_URL="$(health_url)"
python3 - <<'PY'
import json
import os

payload = {
    "backend_url": os.environ["OPENCODE_PREVIEW_RESULT_BACKEND_URL"],
    "health_url": os.environ["OPENCODE_PREVIEW_RESULT_HEALTH_URL"],
    "reviewer_notes": (
        "Manual test user: e2e-smoke@example.com / smoke-test-password. "
        "Preview login has two-factor disabled for this seeded reviewer account."
    ),
}
print(json.dumps(payload, ensure_ascii=True))
PY
