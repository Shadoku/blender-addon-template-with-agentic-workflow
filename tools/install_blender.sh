#!/usr/bin/env bash
# Download the Blender version pinned in .blender-version (or $BLENDER_VERSION) into
# ~/.cache/blender/<version>/blender and print that path on the last line.
# Idempotent: a cached, working binary is reused. Used by CI and the Claude session hook.
# Linux x86_64 and macOS only; on Windows install Blender and set BLENDER=<path to blender.exe>.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${BLENDER_VERSION:-$(cat "$ROOT/.blender-version" 2>/dev/null || echo 5.2.3)}"
CACHE="${BLENDER_CACHE_DIR:-$HOME/.cache/blender}"
DEST="$CACHE/$VERSION"
BIN="$DEST/blender"
MAJOR_MINOR="${VERSION%.*}"

if [ -x "$BIN" ] && "$BIN" --version >/dev/null 2>&1; then
  echo "$BIN"
  exit 0
fi

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)  ASSET="blender-${VERSION}-linux-x64.tar.xz" ;;
  Darwin-arm64)  ASSET="blender-${VERSION}-macos-arm64.dmg" ;;
  Darwin-x86_64) ASSET="blender-${VERSION}-macos-x64.dmg" ;;
  *) echo "install_blender.sh: unsupported platform $(uname -s)-$(uname -m); install Blender manually and set BLENDER=/path/to/blender" >&2; exit 1 ;;
esac

URL="https://download.blender.org/release/Blender${MAJOR_MINOR}/${ASSET}"
echo "Downloading $URL" >&2
mkdir -p "$DEST"
TMP="$DEST/$ASSET"
curl -fsSL --retry 3 --retry-delay 2 -o "$TMP" "$URL"

case "$ASSET" in
  *.tar.xz)
    tar -xJf "$TMP" -C "$DEST" --strip-components=1
    ;;
  *.dmg)
    MNT="$(mktemp -d)"
    hdiutil attach -nobrowse -quiet -mountpoint "$MNT" "$TMP"
    cp -R "$MNT/Blender.app" "$DEST/"
    hdiutil detach -quiet "$MNT"
    ln -sf "$DEST/Blender.app/Contents/MacOS/Blender" "$BIN"
    ;;
esac
rm -f "$TMP"

"$BIN" --version >&2
echo "$BIN"
