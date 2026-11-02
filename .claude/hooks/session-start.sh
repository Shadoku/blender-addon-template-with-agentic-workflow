#!/bin/bash
# SessionStart hook for Claude Code on the web: make a Blender binary and the dev
# dependencies available so `python3 tools/check.py` works. Does nothing outside
# the remote environment (locally, install Blender yourself or run tools/install_blender.sh).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Mesa gives headless Blender the libEGL that Workbench renders need; without it the
# render tests skip (and a render outside them makes Blender exit). Best effort only.
MESA_PACKAGES="libegl1 libgl1 libgles2 libglx-mesa0 libgl1-mesa-dri libegl-mesa0"
if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
  # shellcheck disable=SC2086
  if { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $MESA_PACKAGES; } >/dev/null 2>&1; then
    echo "Mesa ready: render tests can run"
  else
    echo "Mesa install failed: render tests will skip"
  fi
else
  echo "Mesa not installed (needs root and apt-get): render tests skip unless libEGL is present"
fi
BIN="$(bash "$ROOT/tools/install_blender.sh" | tail -n 1)"

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export BLENDER=\"$BIN\"" >> "$CLAUDE_ENV_FILE"
fi

# Install pytest/ruff into .blender-deps with Blender's bundled pip so the first check is fast.
(cd "$ROOT" && BLENDER="$BIN" python3 tools/check.py --setup >/dev/null 2>&1) || true
echo "Blender ready: $BIN"
