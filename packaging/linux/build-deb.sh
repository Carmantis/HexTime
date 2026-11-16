#!/usr/bin/env bash
# Builds the .deb from the PyInstaller build.
#
#   ./packaging/build-app.sh            # first, builds backend/dist/hextime/
#   ./packaging/linux/build-deb.sh      # writes packaging/output/hextime_<version>_amd64.deb
#
# Needs nfpm on PATH (CI installs it; locally: https://nfpm.goreleaser.com/install/).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$ROOT/packaging/output"

BUILD_DIR="$ROOT/backend/dist/hextime"
if [[ ! -x "$BUILD_DIR/hextime" ]]; then
  echo "No build found at $BUILD_DIR. Run ./packaging/build-app.sh first." >&2
  exit 1
fi

# One version for everything: the backend's. nfpm.yaml reads it as ${VERSION}.
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/backend/pyproject.toml" | head -n1)"
export VERSION

# Everything nfpm packs, in one folder, so nfpm.yaml can use plain relative
# paths (nfpm does not expand variables in file paths).
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -a "$BUILD_DIR" "$STAGE/app"
cp -a "$ROOT/packaging/icons" "$STAGE/icons"
cp "$HERE/nfpm.yaml" "$STAGE/"
# The menu entry points at the installed program.
sed "s|^Exec=.*|Exec=/opt/hextime/hextime|" "$HERE/hextime.desktop" >"$STAGE/hextime.desktop"

mkdir -p "$OUT"
(cd "$STAGE" && nfpm package --config nfpm.yaml --packager deb --target "$OUT/")
echo "==> Done: $OUT/hextime_${VERSION}_amd64.deb"
