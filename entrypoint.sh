#!/bin/sh
set -e

APP_USER=${APP_USER:-app}
APP_GROUP=${APP_GROUP:-app}
DB_PATH=${DB_PATH:-/app/db/db.sqlite3}
MEDIA_ROOT=${MEDIA_ROOT:-/app/media}

export APP_USER
export APP_GROUP
export DB_PATH
export MEDIA_ROOT

DB_DIR=$(dirname "$DB_PATH")
mkdir -p "$DB_DIR" "$MEDIA_ROOT"

if [ "$(id -u)" = "0" ]; then
  chown -R "${APP_USER}:${APP_GROUP}" "$DB_DIR" "$MEDIA_ROOT"
  chmod -R u+rwX,g+rwX "$DB_DIR" "$MEDIA_ROOT"
  exec su-exec "${APP_USER}:${APP_GROUP}" "$0" "$@"
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
