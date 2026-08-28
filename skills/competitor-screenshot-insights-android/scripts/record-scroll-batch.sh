#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/agent-device-env.sh"

usage() {
  echo "Usage: record-scroll-batch.sh --output /absolute/path.mp4 --count N [--session NAME --x N --y N --dx N --dy N --duration-ms N --pause-seconds N --fps N --quality medium|high] [--dry-run]" >&2
}

OUTPUT=
COUNT=
X=195
Y=650
DX=0
DY=-400
DURATION_MS=800
PAUSE_SECONDS=0.7
FPS=30
QUALITY=high
DRY_RUN=0
SESSION=$AGENT_DEVICE_SESSION

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) OUTPUT=${2-}; shift 2 ;;
    --count) COUNT=${2-}; shift 2 ;;
    --session) SESSION=${2-}; shift 2 ;;
    --x) X=${2-}; shift 2 ;;
    --y) Y=${2-}; shift 2 ;;
    --dx) DX=${2-}; shift 2 ;;
    --dy) DY=${2-}; shift 2 ;;
    --duration-ms) DURATION_MS=${2-}; shift 2 ;;
    --pause-seconds) PAUSE_SECONDS=${2-}; shift 2 ;;
    --fps) FPS=${2-}; shift 2 ;;
    --quality) QUALITY=${2-}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage; echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$OUTPUT" in
  /*.mp4) ;;
  *) usage; echo "--output must be an absolute .mp4 path" >&2; exit 2 ;;
esac
case "$COUNT" in
  ''|*[!0-9]*) usage; echo "--count must be a positive integer" >&2; exit 2 ;;
esac
if [ "$COUNT" -le 0 ]; then
  usage
  echo "--count must be greater than zero" >&2
  exit 2
fi
case "$QUALITY" in
  medium|high) ;;
  *) usage; echo "--quality must be medium or high" >&2; exit 2 ;;
esac
if [ -z "$SESSION" ]; then
  usage
  echo "--session must not be empty" >&2
  exit 2
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '{\n  "decision": "dry_run",\n  "output": "%s",\n  "count": %s,\n  "session": "%s",\n  "gesture": {"x": %s, "y": %s, "dx": %s, "dy": %s, "duration_ms": %s},\n  "pause_seconds": %s,\n  "fps": %s,\n  "quality": "%s"\n}\n' \
    "$OUTPUT" "$COUNT" "$SESSION" "$X" "$Y" "$DX" "$DY" "$DURATION_MS" "$PAUSE_SECONDS" "$FPS" "$QUALITY"
  exit 0
fi

RECORDING=0
cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$RECORDING" -eq 1 ]; then
    agent-device record stop --session "$SESSION" --json || true
  fi
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

agent-device record start "$OUTPUT" --fps "$FPS" --quality "$QUALITY" --hide-touches --session "$SESSION" --json
RECORDING=1

i=1
while [ "$i" -le "$COUNT" ]; do
  agent-device gesture pan "$X" "$Y" "$DX" "$DY" "$DURATION_MS" --session "$SESSION" --json
  sleep "$PAUSE_SECONDS"
  i=$((i + 1))
done

if agent-device record stop --session "$SESSION" --json; then
  RECORDING=0
else
  RECORDING=0
  exit 1
fi
trap - EXIT HUP INT TERM
