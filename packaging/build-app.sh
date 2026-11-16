#!/usr/bin/env bash
# Builds the desktop app into backend/dist/hextime/ (Linux or Windows/Git Bash).
#
#   ./packaging/build-app.sh
#
# The UI is compiled first, because the bundle serves it from app/static.
# The installers (packaging/linux, packaging/windows) package this folder.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Building the UI"
(cd "$ROOT/frontend" && npm ci && npm run build)

echo "==> Bundling the app with PyInstaller"
(
  cd "$ROOT/backend"
  rm -rf build dist
  uv sync --frozen --extra desktop
  uv run --frozen --extra desktop pyinstaller hextime.spec --noconfirm
)

echo "==> Done: $ROOT/backend/dist/hextime/"
