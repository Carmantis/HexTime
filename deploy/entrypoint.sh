#!/bin/sh
# Start HexTime in the container: migrate the database, then serve.
#
# Any arguments run instead of the server, with the same environment, so
# maintenance commands work through the same image:
#
#   podman exec -it hextime hextime-entrypoint python -m app.cli create-admin ...
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# PostgreSQL may still be starting the first time: wait for it to answer,
# for a while. Then migrate once. A failed migration (a wrong password, an
# image older than the database) is not something trying again fixes, so it
# stops here with its own error rather than a vague retry loop.
python -m app.core.db_wait --timeout 90
if ! alembic upgrade head; then
  echo "hextime: migrating the database failed (the error is above); not starting." >&2
  exit 1
fi

# --proxy-headers: Caddy terminates TLS and tells us the client's address and
# scheme. Only Caddy can reach this port (it is not published), so trusting
# the forwarded headers from any address is safe here.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips '*' \
  --no-server-header
