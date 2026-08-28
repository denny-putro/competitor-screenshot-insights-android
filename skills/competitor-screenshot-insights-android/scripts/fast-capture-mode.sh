#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMMAND=${1:-}
FAST_CAPTURE_PYTHON=${CSI_FAST_CAPTURE_PYTHON:-}

case "$COMMAND" in
  start|capture)
    if PREFLIGHT_RESULT=$(sh "$SCRIPT_DIR/preflight.sh"); then
      :
    else
      PREFLIGHT_STATUS=$?
      printf '%s\n' "$PREFLIGHT_RESULT"
      exit "$PREFLIGHT_STATUS"
    fi
    . "$SCRIPT_DIR/agent-device-env.sh"
    FAST_CAPTURE_PYTHON=$SCREENSHOT_STITCHER_PYTHON
    ;;
esac

if [ -z "$FAST_CAPTURE_PYTHON" ]; then
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      CANDIDATE_PATH=$(command -v "$candidate")
      if "$CANDIDATE_PATH" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        FAST_CAPTURE_PYTHON=$CANDIDATE_PATH
        break
      fi
    fi
  done
fi

if [ -z "$FAST_CAPTURE_PYTHON" ] || [ ! -x "$FAST_CAPTURE_PYTHON" ]; then
  printf '%s\n' '{"status":"failed","reason":"Python 3.10 or newer is required for fast-capture routing"}'
  exit 2
fi

exec "$FAST_CAPTURE_PYTHON" "$SCRIPT_DIR/fast_capture_mode.py" "$@"
