#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SCHEMA_VERSION=4
CONFIG_LOADER="$SCRIPT_DIR/agent-device-env.sh"
if [ -n "${CSI_AGENT_DEVICE_ENV:-}" ]; then
  CONFIG_FILE=$CSI_AGENT_DEVICE_ENV
elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
  CONFIG_FILE="$XDG_CONFIG_HOME/competitor-screenshot-insights/agent-device-env.sh"
elif [ -n "${HOME:-}" ]; then
  CONFIG_FILE="$HOME/.config/competitor-screenshot-insights/agent-device-env.sh"
else
  printf '%s\n' '{"status":"error","reason":"config_location_unavailable"}'
  exit 2
fi
MODE=check
REASONS=

case "${1:-}" in
  "") ;;
  --record) MODE=record ;;
  --help)
    printf '%s\n' 'usage: scripts/preflight.sh [--record]'
    exit 0
    ;;
  *)
    printf '%s\n' '{"status":"error","reason":"invalid_argument"}'
    exit 2
    ;;
esac

if [ -n "${CSI_INSTALL_STATE:-}" ]; then
  STATE_FILE=$CSI_INSTALL_STATE
elif [ -n "${XDG_STATE_HOME:-}" ]; then
  STATE_FILE="$XDG_STATE_HOME/competitor-screenshot-insights/install-state.json"
elif [ -n "${HOME:-}" ]; then
  STATE_FILE="$HOME/.local/state/competitor-screenshot-insights/install-state.json"
else
  printf '%s\n' '{"status":"error","reason":"state_location_unavailable"}'
  exit 2
fi

add_reason() {
  if [ -z "$REASONS" ]; then
    REASONS=$1
  else
    REASONS="$REASONS,$1"
  fi
}

print_reason_array() {
  old_ifs=$IFS
  IFS=,
  first=1
  printf '['
  for reason in $REASONS; do
    if [ "$first" -eq 0 ]; then
      printf ','
    fi
    printf '"%s"' "$reason"
    first=0
  done
  printf ']'
  IFS=$old_ifs
}

emit_setup_required() {
  printf '{"status":"setup_required","reasons":'
  print_reason_array
  printf '%s\n' ',"next_action":"read_install"}'
}

require_value() {
  value=$1
  reason=$2
  if [ -z "$value" ]; then
    add_reason "$reason"
  fi
}

require_directory() {
  path=$1
  reason=$2
  if [ -z "$path" ] || [ ! -d "$path" ]; then
    add_reason "$reason"
  fi
}

require_executable() {
  path=$1
  reason=$2
  if [ -z "$path" ] || [ ! -x "$path" ]; then
    add_reason "$reason"
  fi
}

require_file() {
  path=$1
  reason=$2
  if [ -z "$path" ] || [ ! -f "$path" ]; then
    add_reason "$reason"
  fi
}

if [ ! -f "$CONFIG_FILE" ]; then
  add_reason config_file_missing
  emit_setup_required
  exit 10
fi

CSI_AGENT_DEVICE_ENV=$CONFIG_FILE
export CSI_AGENT_DEVICE_ENV
. "$CONFIG_LOADER"

NODE_BIN="${AGENT_DEVICE_NODE_BIN:-}/node"
AGENT_DEVICE_EXECUTABLE=${AGENT_DEVICE_RAW_BIN:-"${AGENT_DEVICE_BIN:-}/agent-device"}
APP_TARGET_RESOLVER="$SCRIPT_DIR/resolve-target-app.py"
APP_TARGET_OPENER="$SCRIPT_DIR/open-mapped-app.sh"
APP_TARGET_GUARD="${AGENT_DEVICE_GUARD_BIN:-$SCRIPT_DIR/guard-bin}/agent-device"
APP_BUNDLE_REGISTRY="$SKILL_ROOT/references/app-bundle-ids.md"
XCODEBUILD_BIN="${DEVELOPER_DIR:-}/usr/bin/xcodebuild"
if [ -x "${DEVELOPER_DIR:-}/usr/bin/xcrun" ]; then
  XCRUN_BIN="${DEVELOPER_DIR:-}/usr/bin/xcrun"
else
  XCRUN_BIN=$(command -v xcrun 2>/dev/null || true)
fi

require_executable "$NODE_BIN" node_missing
require_executable "$AGENT_DEVICE_EXECUTABLE" agent_device_missing
require_executable "$APP_TARGET_RESOLVER" target_resolver_missing
require_executable "$APP_TARGET_OPENER" target_opener_missing
require_executable "$APP_TARGET_GUARD" target_open_guard_missing
require_file "$APP_BUNDLE_REGISTRY" app_bundle_registry_missing
require_directory "${AGENT_DEVICE_XCODE_APP:-}" xcode_app_missing
require_directory "${DEVELOPER_DIR:-}" developer_dir_missing
require_executable "$XCODEBUILD_BIN" xcodebuild_missing
require_executable "$XCRUN_BIN" xcrun_missing
require_directory "${SCREENSHOT_STITCHER_HOME:-}" screenshot_environment_missing
require_executable "${SCREENSHOT_STITCHER_PYTHON:-}" screenshot_python_missing
require_executable "${SCREENSHOT_STITCHER_BIN:-}" screenshot_stitcher_missing
require_value "${AGENT_DEVICE_DEVICE:-}" device_configuration_missing
require_value "${AGENT_DEVICE_IOS_TEAM_ID:-}" team_id_missing
require_value "${AGENT_DEVICE_IOS_BUNDLE_ID:-}" runner_bundle_id_missing
require_value "${AGENT_DEVICE_SESSION:-}" session_name_missing

if { [ -n "${CSI_VIEWPORT_WIDTH:-}" ] && [ -z "${CSI_VIEWPORT_HEIGHT:-}" ]; } || \
   { [ -z "${CSI_VIEWPORT_WIDTH:-}" ] && [ -n "${CSI_VIEWPORT_HEIGHT:-}" ]; }; then
  add_reason coordinate_viewport_configuration_incomplete
fi

if [ "${AGENT_DEVICE_PLATFORM:-}" != ios ]; then
  add_reason ios_platform_configuration_missing
fi

if [ -x "$APP_TARGET_RESOLVER" ] && [ -f "$APP_BUNDLE_REGISTRY" ] && ! "$APP_TARGET_RESOLVER" --registry "$APP_BUNDLE_REGISTRY" validate >/dev/null 2>&1; then
  add_reason app_bundle_registry_invalid
fi

if command -v shasum >/dev/null 2>&1; then
  HASH_KIND=shasum
elif command -v sha256sum >/dev/null 2>&1; then
  HASH_KIND=sha256sum
else
  HASH_KIND=
  add_reason sha256_tool_missing
fi

if [ -n "$REASONS" ]; then
  emit_setup_required
  exit 10
fi

digest_stream() {
  case "$HASH_KIND" in
    shasum) shasum -a 256 | sed 's/[[:space:]].*$//' ;;
    sha256sum) sha256sum | sed 's/[[:space:]].*$//' ;;
  esac
}

digest_files() {
  case "$HASH_KIND" in
    shasum) shasum -a 256 "$@" ;;
    sha256sum) sha256sum "$@" ;;
  esac
}

file_signatures() {
  if stat -f '%N:%m:%z' "$1" >/dev/null 2>&1; then
    stat -f '%N:%m:%z' "$@"
  else
    stat -c '%n:%Y:%s' "$@"
  fi
}

fingerprint_material() {
  printf 'schema=%s\n' "$SCHEMA_VERSION"
  digest_files \
    "$CONFIG_FILE" \
    "$CONFIG_LOADER" \
    "$SKILL_ROOT/SKILL.md" \
    "$SKILL_ROOT/INSTALL.md" \
    "$APP_BUNDLE_REGISTRY" \
    "$SKILL_ROOT/requirements-runtime.txt" \
    "$SKILL_ROOT/requirements-eval.txt" \
    "$SCRIPT_DIR/setup.sh" \
    "$SCRIPT_DIR/preflight.sh" \
    "$APP_TARGET_RESOLVER" \
    "$APP_TARGET_OPENER" \
    "$APP_TARGET_GUARD"
  file_signatures \
    "$NODE_BIN" \
    "$AGENT_DEVICE_EXECUTABLE" \
    "$XCODEBUILD_BIN" \
    "$XCRUN_BIN" \
    "$SCREENSHOT_STITCHER_PYTHON" \
    "$SCREENSHOT_STITCHER_BIN"
}

CURRENT_FINGERPRINT=$(fingerprint_material | digest_stream)

read_state_value() {
  key=$1
  sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$STATE_FILE" | sed -n '1p'
}

read_state_number() {
  key=$1
  sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p" "$STATE_FILE" | sed -n '1p'
}

if [ "$MODE" = check ]; then
  if [ ! -f "$STATE_FILE" ]; then
    add_reason install_state_missing
    emit_setup_required
    exit 10
  fi

  STORED_STATUS=$(read_state_value status)
  STORED_SCHEMA=$(read_state_number schema_version)
  STORED_FINGERPRINT=$(read_state_value fingerprint)

  if [ "$STORED_STATUS" != ready ] || [ "$STORED_SCHEMA" != "$SCHEMA_VERSION" ]; then
    add_reason install_state_invalid
    emit_setup_required
    exit 10
  fi

  if [ "$STORED_FINGERPRINT" != "$CURRENT_FINGERPRINT" ]; then
    add_reason installation_state_stale
    emit_setup_required
    exit 10
  fi

  printf '%s\n' '{"status":"ready","cached":true}'
  exit 0
fi

NODE_VERSION=$("$NODE_BIN" --version 2>/dev/null || true)
node_numeric=${NODE_VERSION#v}
node_major=${node_numeric%%.*}
node_remainder=${node_numeric#*.}
node_minor=${node_remainder%%.*}
case "$node_major:$node_minor" in
  *[!0-9:]*|:*) add_reason node_version_unreadable ;;
  *)
    if [ "$node_major" -lt 22 ] || { [ "$node_major" -eq 22 ] && [ "$node_minor" -lt 12 ]; }; then
      add_reason node_version_incompatible
    fi
    ;;
esac

AGENT_DEVICE_VERSION=$("$AGENT_DEVICE_EXECUTABLE" --version 2>/dev/null || true)
case "$AGENT_DEVICE_VERSION" in
  0.20.*) ;;
  *) add_reason agent_device_version_incompatible ;;
esac

PYTHON_VERSION=$($SCREENSHOT_STITCHER_PYTHON --version 2>&1 || true)
python_numeric=${PYTHON_VERSION#Python }
python_major=${python_numeric%%.*}
python_remainder=${python_numeric#*.}
python_minor=${python_remainder%%.*}
case "$python_major:$python_minor" in
  *[!0-9:]*|:*) add_reason screenshot_python_version_unreadable ;;
  *)
    if [ "$python_major" -ne 3 ] || [ "$python_minor" -lt 12 ]; then
      add_reason screenshot_python_version_incompatible
    fi
    ;;
esac

if ! "$SCREENSHOT_STITCHER_PYTHON" -c 'import cv2, numpy' >/dev/null 2>&1; then
  add_reason screenshot_python_import_failed
fi

if ! "$SCREENSHOT_STITCHER_BIN" --help >/dev/null 2>&1; then
  add_reason screenshot_stitcher_unusable
fi

XCODE_VERSION=$("$XCODEBUILD_BIN" -version 2>/dev/null || true)
if [ -z "$XCODE_VERSION" ]; then
  add_reason xcode_version_unreadable
fi

IPHONEOS_SDK_VERSION=$("$XCRUN_BIN" --sdk iphoneos --show-sdk-version 2>/dev/null || true)
if [ -z "$IPHONEOS_SDK_VERSION" ]; then
  add_reason iphoneos_sdk_unavailable
fi

if [ -n "$REASONS" ]; then
  emit_setup_required
  exit 10
fi

if [ "${CSI_PREFLIGHT_SKIP_TESTS:-0}" != 1 ]; then
  if ! sh "$SCRIPT_DIR/run-tests.sh" >/dev/null 2>&1; then
    add_reason skill_tests_failed
    emit_setup_required
    exit 10
  fi
fi

json_string() {
  printf '%s' "$1" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g; s/[[:space:]][[:space:]]*/ /g; s/[[:space:]]$//'
}

STATE_DIR=$(dirname -- "$STATE_FILE")
mkdir -p "$STATE_DIR"
umask 077
TEMP_STATE=$(mktemp "$STATE_DIR/.install-state.XXXXXX")
trap 'rm -f "$TEMP_STATE"' EXIT HUP INT TERM
RECORDED_AT=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

{
  printf '%s\n' '{'
  printf '  "schema_version": %s,\n' "$SCHEMA_VERSION"
  printf '%s\n' '  "status": "ready",'
  printf '  "fingerprint": "%s",\n' "$CURRENT_FINGERPRINT"
  printf '  "recorded_at": "%s",\n' "$RECORDED_AT"
  printf '%s\n' '  "versions": {'
  printf '    "node": "%s",\n' "$(json_string "$NODE_VERSION")"
  printf '    "agent_device": "%s",\n' "$(json_string "$AGENT_DEVICE_VERSION")"
  printf '    "python": "%s",\n' "$(json_string "$PYTHON_VERSION")"
  printf '    "xcode": "%s",\n' "$(json_string "$XCODE_VERSION")"
  printf '    "iphoneos_sdk": "%s"\n' "$(json_string "$IPHONEOS_SDK_VERSION")"
  printf '%s\n' '  }'
  printf '%s\n' '}'
} > "$TEMP_STATE"

mv "$TEMP_STATE" "$STATE_FILE"
trap - EXIT HUP INT TERM
printf '%s\n' '{"status":"ready","cached":false,"recorded":true}'
