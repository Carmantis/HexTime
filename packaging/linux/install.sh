#!/usr/bin/env bash
# Installs the built app for the current user, on any Linux distribution,
# so it appears in the application menu (Omarchy's launcher included).
#
#   ./packaging/build-app.sh            # first, builds backend/dist/hextime/
#   ./packaging/linux/install.sh        # install or update
#   ./packaging/linux/install.sh --uninstall
#
# Everything goes under ~/.local; nothing needs root. Your data is not touched:
# it lives in ~/.local/share/HexTime/ and stays there even after --uninstall.
#
# Needs the system's GTK 3 and WebKitGTK 4.1 (on Arch: the webkit2gtk-4.1
# package). Python is not needed: it is inside the build. The .deb declares
# these itself.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"

APP_DIR="$PREFIX/lib/hextime"
BIN="$PREFIX/bin/hextime"
DESKTOP="$PREFIX/share/applications/hextime.desktop"
ICONS="$PREFIX/share/icons/hicolor"

refresh_menus() {
  # Let menus and launchers notice the change; harmless where missing.
  command -v update-desktop-database >/dev/null &&
    update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
  command -v gtk-update-icon-cache >/dev/null &&
    gtk-update-icon-cache -q -t "$ICONS" 2>/dev/null || true
}

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -rf "${APP_DIR:?}"
  rm -f "$BIN" "$DESKTOP" \
    "$ICONS/scalable/apps/hextime.svg" "$ICONS/256x256/apps/hextime.png"
  refresh_menus
  echo "HexTime removed. Your data is still in ~/.local/share/HexTime/."
  exit 0
fi

BUILD="$ROOT/backend/dist/hextime"
if [[ ! -x "$BUILD/hextime" ]]; then
  echo "No build found at $BUILD. Run ./packaging/build-app.sh first." >&2
  exit 1
fi

echo "==> Installing to $APP_DIR"
rm -rf "${APP_DIR:?}"
mkdir -p "$APP_DIR" "$(dirname "$BIN")" "$(dirname "$DESKTOP")" \
  "$ICONS/scalable/apps" "$ICONS/256x256/apps"
cp -a "$BUILD/." "$APP_DIR/"
ln -sf "$APP_DIR/hextime" "$BIN"

cp "$ROOT/packaging/icons/hextime.svg" "$ICONS/scalable/apps/hextime.svg"
cp "$ROOT/packaging/icons/hextime-256.png" "$ICONS/256x256/apps/hextime.png"

# An absolute Exec, so the menu entry works even if ~/.local/bin is not on PATH.
sed "s|^Exec=.*|Exec=$APP_DIR/hextime|" "$ROOT/packaging/linux/hextime.desktop" >"$DESKTOP"

refresh_menus
echo "==> Done. HexTime is in the application menu; or run: $BIN"
