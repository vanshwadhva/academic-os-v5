#!/bin/sh
# Runs as root only long enough to fix ownership of the runtime volume, which
# platforms (Render, Compose) mount as root. Then it drops to the app user.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/runtime
  chown -R appuser:appuser /app/runtime
  exec gosu appuser "$@"
fi
exec "$@"
