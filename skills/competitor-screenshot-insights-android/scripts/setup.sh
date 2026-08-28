#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEVICE=
SERIAL=
SESSION=phone-main
NODE_BIN_DIR=
AGENT_DEVICE_BIN_DIR=
ANDROID_SDK=
ADB_BIN=
STITCHER_HOME=
VIEWPORT_WIDTH=
VIEWPORT_HEIGHT=

if [ -n "${CSI_AGENT_DEVICE_ENV:-}" ]; then
  CONFIG_FILE=$CSI_AGENT_DEVICE_ENV
elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
  CONFIG_FILE="$XDG_CONFIG_HOME/competitor-screenshot-insights-android/agent-device-env.sh"
elif [ -n "${HOME:-}" ]; then
  CONFIG_FILE="$HOME/.config/competitor-screenshot-insights-android/agent-device-env.sh"
else
  printf '%s\n' '{"status":"error","reason":"config_location_unavailable"}'
  exit 2
fi

usage() {
  printf '%s\n' 'usage: scripts/setup.sh --device <name> [--serial <adb-serial>] [--session <name>] [--node-bin <dir>] [--agent-device-bin <dir>] [--android-sdk <dir>] [--adb <file>] [--stitcher-home <venv>] [--viewport-width <points> --viewport-height <points>] [--config <file>]'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --device) DEVICE=${2:-}; shift 2 ;;
    --serial) SERIAL=${2:-}; shift 2 ;;
    --session) SESSION=${2:-}; shift 2 ;;
    --node-bin) NODE_BIN_DIR=${2:-}; shift 2 ;;
    --agent-device-bin) AGENT_DEVICE_BIN_DIR=${2:-}; shift 2 ;;
    --android-sdk) ANDROID_SDK=${2:-}; shift 2 ;;
    --adb) ADB_BIN=${2:-}; shift 2 ;;
    --stitcher-home) STITCHER_HOME=${2:-}; shift 2 ;;
    --viewport-width) VIEWPORT_WIDTH=${2:-}; shift 2 ;;
    --viewport-height) VIEWPORT_HEIGHT=${2:-}; shift 2 ;;
    --config) CONFIG_FILE=${2:-}; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

# Android needs no signing identity, so the device name is the only required
# identity value. Never infer it from another machine's configuration.
if [ -z "$DEVICE" ]; then
  usage >&2
  printf '%s\n' '{"status":"setup_required","reasons":["device_is_required"]}'
  exit 10
fi

if { [ -n "$VIEWPORT_WIDTH" ] && [ -z "$VIEWPORT_HEIGHT" ]; } || \
   { [ -z "$VIEWPORT_WIDTH" ] && [ -n "$VIEWPORT_HEIGHT" ]; }; then
  printf '%s\n' '{"status":"setup_required","reasons":["both_viewport_dimensions_are_required"]}'
  exit 10
fi

if [ -z "$NODE_BIN_DIR" ]; then
  NODE_EXECUTABLE=$(command -v node 2>/dev/null || true)
  [ -n "$NODE_EXECUTABLE" ] && NODE_BIN_DIR=$(dirname -- "$NODE_EXECUTABLE")
fi

if [ -z "$AGENT_DEVICE_BIN_DIR" ]; then
  AGENT_DEVICE_EXECUTABLE=$(command -v agent-device 2>/dev/null || true)
  [ -n "$AGENT_DEVICE_EXECUTABLE" ] && AGENT_DEVICE_BIN_DIR=$(dirname -- "$AGENT_DEVICE_EXECUTABLE")
fi

# Agent Device resolves adb through ANDROID_HOME, ANDROID_SDK_ROOT, or PATH.
# Discover the SDK the same way so the recorded configuration is explicit.
if [ -z "$ANDROID_SDK" ]; then
  if [ -n "${ANDROID_HOME:-}" ]; then
    ANDROID_SDK=$ANDROID_HOME
  elif [ -n "${ANDROID_SDK_ROOT:-}" ]; then
    ANDROID_SDK=$ANDROID_SDK_ROOT
  elif [ -n "${HOME:-}" ] && [ -d "$HOME/Library/Android/sdk" ]; then
    ANDROID_SDK="$HOME/Library/Android/sdk"
  fi
fi

if [ -z "$ADB_BIN" ]; then
  if [ -n "$ANDROID_SDK" ] && [ -x "$ANDROID_SDK/platform-tools/adb" ]; then
    ADB_BIN="$ANDROID_SDK/platform-tools/adb"
  else
    ADB_BIN=$(command -v adb 2>/dev/null || true)
  fi
fi

if [ -z "$STITCHER_HOME" ]; then
  STITCHER_EXECUTABLE=$(command -v screenshot-stitcher 2>/dev/null || true)
  if [ -n "$STITCHER_EXECUTABLE" ]; then
    STITCHER_HOME=$(CDPATH= cd -- "$(dirname -- "$STITCHER_EXECUTABLE")/.." && pwd)
  elif [ -n "${HOME:-}" ] && [ -x "$HOME/.local/share/screenshot-stitcher/bin/screenshot-stitcher" ]; then
    STITCHER_HOME="$HOME/.local/share/screenshot-stitcher"
  fi
fi

REASONS=
add_reason() {
  if [ -z "$REASONS" ]; then REASONS=$1; else REASONS="$REASONS,$1"; fi
}

[ -x "${NODE_BIN_DIR:-}/node" ] || add_reason node_missing
[ -x "${AGENT_DEVICE_BIN_DIR:-}/agent-device" ] || add_reason agent_device_missing
[ -x "${ADB_BIN:-}" ] || add_reason adb_missing
[ -x "${STITCHER_HOME:-}/bin/python" ] || add_reason screenshot_python_missing
[ -x "${STITCHER_HOME:-}/bin/screenshot-stitcher" ] || add_reason screenshot_stitcher_missing

if [ -n "$REASONS" ]; then
  printf '{"status":"setup_required","reasons":['
  old_ifs=$IFS
  IFS=,
  first=1
  for reason in $REASONS; do
    [ "$first" -eq 1 ] || printf ','
    printf '"%s"' "$reason"
    first=0
  done
  IFS=$old_ifs
  printf '%s\n' ']}'
  exit 10
fi

shell_quote() {
  escaped=$(printf '%s' "$1" | sed "s/'/'\\\\''/g")
  printf "'%s'" "$escaped"
}

CONFIG_DIR=$(dirname -- "$CONFIG_FILE")
mkdir -p "$CONFIG_DIR"
umask 077
TEMP_CONFIG=$(mktemp "$CONFIG_DIR/.agent-device-env.XXXXXX")
trap 'rm -f "$TEMP_CONFIG"' EXIT HUP INT TERM

{
  printf 'AGENT_DEVICE_NODE_BIN=%s\n' "$(shell_quote "$NODE_BIN_DIR")"
  printf 'AGENT_DEVICE_BIN=%s\n' "$(shell_quote "$AGENT_DEVICE_BIN_DIR")"
  printf 'AGENT_DEVICE_GUARD_BIN=%s\n' "$(shell_quote "$SCRIPT_DIR/guard-bin")"
  printf 'ANDROID_HOME=%s\n' "$(shell_quote "$ANDROID_SDK")"
  printf 'ANDROID_SDK_ROOT=%s\n' "$(shell_quote "$ANDROID_SDK")"
  printf 'CSI_ADB_BIN=%s\n' "$(shell_quote "$ADB_BIN")"
  printf 'SCREENSHOT_STITCHER_HOME=%s\n' "$(shell_quote "$STITCHER_HOME")"
  printf 'SCREENSHOT_STITCHER_PYTHON=%s\n' "$(shell_quote "$STITCHER_HOME/bin/python")"
  printf 'SCREENSHOT_STITCHER_BIN=%s\n' "$(shell_quote "$STITCHER_HOME/bin/screenshot-stitcher")"
  printf '%s\n' "AGENT_DEVICE_PLATFORM='android'"
  printf 'AGENT_DEVICE_DEVICE=%s\n' "$(shell_quote "$DEVICE")"
  printf 'AGENT_DEVICE_SERIAL=%s\n' "$(shell_quote "$SERIAL")"
  printf 'AGENT_DEVICE_SESSION=%s\n' "$(shell_quote "$SESSION")"
  printf 'CSI_VIEWPORT_WIDTH=%s\n' "$(shell_quote "$VIEWPORT_WIDTH")"
  printf 'CSI_VIEWPORT_HEIGHT=%s\n' "$(shell_quote "$VIEWPORT_HEIGHT")"
} > "$TEMP_CONFIG"

mv "$TEMP_CONFIG" "$CONFIG_FILE"
trap - EXIT HUP INT TERM
printf '%s\n' '{"status":"configured","next_action":"run_preflight_record"}'
