#!/usr/bin/env bash
# Runs HexTime in server mode on this machine, to try out accounts and teams.
# Never for a real server: the secret key and the passwords are public.
#
#   ./scripts/dev-server.sh            # build the UI, add demo data, start on :8000
#   ./scripts/dev-server.sh --reset    # start over from an empty database
#   ./scripts/dev-server.sh --empty    # no demo data (create users yourself)
#   ./scripts/dev-server.sh --no-build # skip the UI build (no frontend changes)
#   ./scripts/dev-server.sh --port 8001
#   ./scripts/dev-server.sh --data-dir DIR  # another database (the e2e tests')
#
# The database is backend/.dev-server/hextime.db, apart from the desktop
# app's own. Emails are not sent: they are printed in this terminal, links
# and all. Stop with Ctrl+C.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$ROOT/backend/.dev-server"
PORT=8000
SEED=1
RESET=0
BUILD=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset) RESET=1 ;;
    --empty) SEED=0 ;;
    --no-build) BUILD=0 ;;
    --port) PORT="${2:?--port needs a number}"; shift ;;
    --data-dir) DATA="$(mkdir -p "${2:?--data-dir needs a directory}" && cd "$2" && pwd)"; shift ;;
    -h | --help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

# Everything below sees these, including every `uv run`. Exported here, in
# the same process, so the server cannot start in local mode by accident.
export APP_MODE=server
export DATABASE_URL="sqlite+pysqlite:///$DATA/hextime.db"
export ALLOWED_EMAIL_DOMAIN=example.org
export PUBLIC_BASE_URL="http://localhost:$PORT"
export SECRET_KEY=dev-only-not-a-secret
export SMTP_HOST=console

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  echo "Port $PORT is in use. Stop what runs there, or use --port." >&2
  exit 1
fi

mkdir -p "$DATA"
if [[ $RESET -eq 1 ]]; then
  echo "==> Starting over with an empty database"
  rm -f "${DATA:?}/hextime.db"
fi

if [[ $BUILD -eq 1 ]]; then
  echo "==> Building the UI"
  (
    cd "$ROOT/frontend"
    [[ -d node_modules ]] || npm ci
    npm run build --silent
  )
fi

cd "$ROOT/backend"

echo "==> Checking the settings"
uv run python -c '
import sys
from app.core.config import get_settings
s = get_settings()
if not s.is_server:
    sys.exit(f"Expected server mode, got {s.app_mode}. Is APP_MODE set in a .env file?")
print(f"    server mode, database {s.database_url}")
'

echo "==> Migrating the database"
uv run alembic upgrade head

if [[ $SEED -eq 1 ]]; then
  echo "==> Demo data"
  uv run python -m scripts.dev_seed
fi

cat <<INFO

  HexTime (server mode): http://localhost:$PORT
INFO
if [[ $SEED -eq 1 ]]; then
  cat <<INFO

  Sign in with any of these, password: hextime-dev-123
    anna@example.org   organisation administrator, in no team
    liisa@example.org  lead of the team "Verkkotiimi"
    mikko@example.org  member of "Verkkotiimi"
    olli@example.org   invited to "Verkkotiimi", asked on sign-in

  One browser keeps one sign-in. For a second person at the same time use a
  private window, another browser, or http://127.0.0.1:$PORT (to the browser
  a different site from localhost, with its own cookies).
INFO
else
  cat <<INFO

  No users yet. In another terminal, from backend/:
    APP_MODE=server DATABASE_URL="$DATABASE_URL" SMTP_HOST=console \\
    PUBLIC_BASE_URL=$PUBLIC_BASE_URL ALLOWED_EMAIL_DOMAIN=example.org SECRET_KEY=x \\
      uv run python -m app.cli create-admin --email you@example.org --name "You" --send-link
INFO
fi
echo
echo "  Emails (invitations, password links) are printed below. Ctrl+C stops."
echo

exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
