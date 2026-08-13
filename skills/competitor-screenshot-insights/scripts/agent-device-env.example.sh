#!/bin/sh

# Copy this file to the private configuration path described in INSTALL.md.
# Never commit the completed file.

AGENT_DEVICE_NODE_BIN="/absolute/path/to/node/bin"
AGENT_DEVICE_BIN="/absolute/path/to/agent-device/bin"
AGENT_DEVICE_GUARD_BIN="/absolute/path/to/skill/scripts/guard-bin"
AGENT_DEVICE_XCODE_APP="/Applications/Xcode.app"
DEVELOPER_DIR="$AGENT_DEVICE_XCODE_APP/Contents/Developer"

SCREENSHOT_STITCHER_HOME="/absolute/path/to/screenshot-stitcher-venv"
SCREENSHOT_STITCHER_PYTHON="$SCREENSHOT_STITCHER_HOME/bin/python"
SCREENSHOT_STITCHER_BIN="$SCREENSHOT_STITCHER_HOME/bin/screenshot-stitcher"

AGENT_DEVICE_PLATFORM="ios"
AGENT_DEVICE_DEVICE="Your iPhone name"
AGENT_DEVICE_IOS_TEAM_ID="YOUR_TEAM_ID"
AGENT_DEVICE_IOS_BUNDLE_ID="com.example.agentdevice.runner"
AGENT_DEVICE_SESSION="phone-main"

# Optional. Configure both values to enable coordinate fallback when a semantic
# snapshot is unavailable. Leave both empty to fail safely instead.
CSI_VIEWPORT_WIDTH=""
CSI_VIEWPORT_HEIGHT=""
