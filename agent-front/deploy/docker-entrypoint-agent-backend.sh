#!/bin/sh
set -eu

runtime_user="${APP_RUNTIME_USER:-app}"
runtime_group="${APP_RUNTIME_GROUP:-app}"

mkdir -p /app/logs /app/data /home/app

chown -R "${runtime_user}:${runtime_group}" /app/logs /app/data /home/app 2>/dev/null || true
chmod -R u+rwX,g+rwX /app/logs /app/data 2>/dev/null || true

if [ -d /app/knowledge ]; then
  chmod -R a+rX /app/knowledge 2>/dev/null || true
fi

if [ "${APP_RUN_AS_ROOT:-0}" = "1" ]; then
  exec "$@"
fi

exec gosu "${runtime_user}:${runtime_group}" "$@"
