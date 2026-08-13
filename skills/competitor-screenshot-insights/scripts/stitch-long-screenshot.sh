#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/agent-device-env.sh"

if [ ! -x "$SCREENSHOT_STITCHER_PYTHON" ] || [ ! -x "$SCREENSHOT_STITCHER_BIN" ]; then
  echo "screenshot-stitcher is not installed at $SCREENSHOT_STITCHER_HOME" >&2
  exit 2
fi

exec "$SCREENSHOT_STITCHER_PYTHON" "$SCRIPT_DIR/stitch_long_screenshot.py" "$@"
