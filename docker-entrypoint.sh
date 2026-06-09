#!/bin/sh
set -eu

runtime_user="${APP_RUNTIME_USER:-app}"
runtime_group="${APP_RUNTIME_GROUP:-app}"

mkdir -p /app/logs /app/data /home/app
chown -R "${runtime_user}:${runtime_group}" /app/logs /app/data /home/app

if [ -d /app/knowledge ]; then
  chmod -R a+rX /app/knowledge || true
fi

exec gosu "${runtime_user}:${runtime_group}" "$@"
