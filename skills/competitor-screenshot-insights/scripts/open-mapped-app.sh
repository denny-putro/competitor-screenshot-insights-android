#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RESOLVER="$SCRIPT_DIR/resolve-target-app.py"
SEED_REGISTRY="$SCRIPT_DIR/../references/app-bundle-ids.md"
REGISTRY=
ENV_FILE="$SCRIPT_DIR/agent-device-env.sh"
TARGET_APP=
SCREENSHOT=
MANIFEST=

usage() {
  printf '%s\n' 'usage: scripts/open-mapped-app.sh --app <registered name/alias or exact installed App name> --screenshot <absolute.png> --manifest <absolute.json> [--registry <absolute.md>]'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app) TARGET_APP=${2:-}; shift 2 ;;
    --screenshot) SCREENSHOT=${2:-}; shift 2 ;;
    --manifest) MANIFEST=${2:-}; shift 2 ;;
    --registry) REGISTRY=${2:-}; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

if [ ! -f "$ENV_FILE" ]; then
  printf '%s\n' "Missing Agent Device environment loader: $ENV_FILE" >&2
  exit 2
fi
. "$ENV_FILE"

if [ -z "$REGISTRY" ]; then
  if [ -n "${CSI_APP_BUNDLE_REGISTRY:-}" ]; then
    REGISTRY=$CSI_APP_BUNDLE_REGISTRY
  elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
    REGISTRY="$XDG_CONFIG_HOME/competitor-screenshot-insights/app-bundle-ids.md"
  elif [ -n "${HOME:-}" ]; then
    REGISTRY="$HOME/.config/competitor-screenshot-insights/app-bundle-ids.md"
  else
    printf '%s\n' 'Unable to resolve the local App registry location.' >&2
    exit 2
  fi
fi

if [ ! -f "$REGISTRY" ]; then
  REGISTRY_DIR=$(dirname -- "$REGISTRY")
  mkdir -p "$REGISTRY_DIR"
  umask 077
  cp "$SEED_REGISTRY" "$REGISTRY"
fi

if [ -z "$TARGET_APP" ] || [ -z "$SCREENSHOT" ] || [ -z "$MANIFEST" ]; then
  usage >&2
  exit 64
fi

RESOLUTION=
MODE=registered
if RESOLUTION=$("$RESOLVER" --registry "$REGISTRY" resolve --app "$TARGET_APP"); then
  BUNDLE_ID=$(printf '%s' "$RESOLUTION" | python3 -c 'import json, sys; print(json.load(sys.stdin)["target"]["bundle_id"])')
else
  RESOLVE_CODE=$?
  if [ "$RESOLVE_CODE" -ne 3 ]; then
    printf '%s\n' "$RESOLUTION" >&2
    exit "$RESOLVE_CODE"
  fi
  MODE=discover
fi

STATE_FILE=$(mktemp)
SNAPSHOT_FILE=$(mktemp)
INVENTORY_FILE=
trap 'rm -f "$STATE_FILE" "$SNAPSHOT_FILE" "$INVENTORY_FILE"' EXIT HUP INT TERM

if [ "$MODE" = discover ]; then
  INVENTORY_FILE=$(mktemp)
  agent-device apps --json > "$INVENTORY_FILE"
  if DISCOVERY=$("$RESOLVER" --registry "$REGISTRY" discover --app "$TARGET_APP" --inventory "$INVENTORY_FILE"); then
    :
  else
    DISCOVERY_CODE=$?
    printf '%s\n' "$DISCOVERY" >&2
    exit "$DISCOVERY_CODE"
  fi
  BUNDLE_ID=$(printf '%s' "$DISCOVERY" | python3 -c 'import json, sys; print(json.load(sys.stdin)["candidate"]["bundle_id"])')
fi

"$AGENT_DEVICE_RAW_BIN" open "$BUNDLE_ID"
agent-device wait 1000
agent-device screenshot "$SCREENSHOT" --normalize-status-bar
agent-device appstate > "$STATE_FILE"
agent-device snapshot --json > "$SNAPSHOT_FILE"
if [ "$MODE" = registered ]; then
  "$RESOLVER" --registry "$REGISTRY" verify \
    --app "$TARGET_APP" \
    --appstate "$STATE_FILE" \
    --snapshot "$SNAPSHOT_FILE" \
    --screenshot "$SCREENSHOT" \
    --manifest "$MANIFEST"
else
  "$RESOLVER" --registry "$REGISTRY" register-discovered \
    --app "$TARGET_APP" \
    --inventory "$INVENTORY_FILE" \
    --appstate "$STATE_FILE" \
    --snapshot "$SNAPSHOT_FILE" \
    --screenshot "$SCREENSHOT" \
    --manifest "$MANIFEST"
fi
