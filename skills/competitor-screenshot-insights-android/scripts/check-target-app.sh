#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/agent-device-env.sh"

exec "$SCREENSHOT_STITCHER_PYTHON" "$SCRIPT_DIR/screenshot_checks.py" target-app "$@"
