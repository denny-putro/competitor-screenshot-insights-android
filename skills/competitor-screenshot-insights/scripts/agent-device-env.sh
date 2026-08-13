#!/bin/sh

# Load private, machine-specific settings without storing them in the Skill.
CSI_ENV_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -n "${CSI_AGENT_DEVICE_ENV:-}" ]; then
  CSI_LOCAL_CONFIG=$CSI_AGENT_DEVICE_ENV
elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
  CSI_LOCAL_CONFIG="$XDG_CONFIG_HOME/competitor-screenshot-insights/agent-device-env.sh"
elif [ -n "${HOME:-}" ]; then
  CSI_LOCAL_CONFIG="$HOME/.config/competitor-screenshot-insights/agent-device-env.sh"
else
  printf '%s\n' 'Unable to resolve the local Competitor Screenshot Insights configuration.' >&2
  return 10 2>/dev/null || exit 10
fi

if [ ! -f "$CSI_LOCAL_CONFIG" ]; then
  printf 'Missing local configuration: %s\n' "$CSI_LOCAL_CONFIG" >&2
  printf '%s\n' 'Run scripts/setup.sh or follow INSTALL.md.' >&2
  return 10 2>/dev/null || exit 10
fi

. "$CSI_LOCAL_CONFIG"

AGENT_DEVICE_GUARD_BIN=${AGENT_DEVICE_GUARD_BIN:-"$CSI_ENV_SCRIPT_DIR/guard-bin"}
AGENT_DEVICE_RAW_BIN=${AGENT_DEVICE_RAW_BIN:-"${AGENT_DEVICE_BIN:-}/agent-device"}
AGENT_DEVICE_PLATFORM=${AGENT_DEVICE_PLATFORM:-ios}
AGENT_DEVICE_SESSION=${AGENT_DEVICE_SESSION:-phone-main}

for CSI_PATH_ENTRY in \
  "$AGENT_DEVICE_GUARD_BIN" \
  "${AGENT_DEVICE_NODE_BIN:-}" \
  "${AGENT_DEVICE_BIN:-}"
do
  [ -n "$CSI_PATH_ENTRY" ] || continue
  case ":$PATH:" in
    *":$CSI_PATH_ENTRY:"*) ;;
    *) PATH="$CSI_PATH_ENTRY:$PATH" ;;
  esac
done

export PATH
export CSI_AGENT_DEVICE_ENV="$CSI_LOCAL_CONFIG"
export AGENT_DEVICE_GUARD_BIN
export AGENT_DEVICE_RAW_BIN
export AGENT_DEVICE_XCODE_APP
export DEVELOPER_DIR
export AGENT_DEVICE_PLATFORM
export AGENT_DEVICE_DEVICE
export AGENT_DEVICE_IOS_TEAM_ID
export AGENT_DEVICE_IOS_BUNDLE_ID
export AGENT_DEVICE_SESSION
export SCREENSHOT_STITCHER_HOME
export SCREENSHOT_STITCHER_PYTHON
export SCREENSHOT_STITCHER_BIN
export CSI_VIEWPORT_WIDTH
export CSI_VIEWPORT_HEIGHT
export CSI_APP_BUNDLE_REGISTRY

unset CSI_ENV_SCRIPT_DIR CSI_LOCAL_CONFIG CSI_PATH_ENTRY
