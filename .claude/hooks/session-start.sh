#!/bin/bash
# SessionStart hook for Claude Code on the web: make a Blender binary and the dev
# dependencies available so `python3 tools/check.py` works. Does nothing outside
# the remote environment (locally, install Blender yourself or run tools/install_blender.sh).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BIN="$(bash "$ROOT/tools/install_blender.sh" | tail -n 1)"

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export BLENDER=\"$BIN\"" >> "$CLAUDE_ENV_FILE"
fi

# Install pytest/ruff into .blender-deps with Blender's bundled pip so the first check is fast.
(cd "$ROOT" && BLENDER="$BIN" python3 tools/check.py --setup >/dev/null 2>&1) || true
echo "Blender ready: $BIN"
