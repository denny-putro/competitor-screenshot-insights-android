#!/bin/sh
# Deploy this repo's skill into ~/.claude/skills/.
#
# A symlink does NOT work: Claude Code's skill discovery does not follow
# symlinks (a symlinked skill is simply not listed), so the skill must exist
# as a real directory. This repo stays the source of truth and deploys by copy.
#
# Usage:
#   sh deploy.sh          copy repo -> ~/.claude/skills, then re-record preflight
#   sh deploy.sh --check   report drift only, change nothing
set -eu

NAME=competitor-screenshot-insights-android
SRC=$(CDPATH= cd -- "$(dirname -- "$0")/skills/$NAME" && pwd)
DEST="$HOME/.claude/skills/$NAME"

if [ "${1:-}" = "--check" ]; then
  if [ ! -d "$DEST" ]; then
    printf '%s\n' "not deployed: $DEST"; exit 1
  fi
  if diff -r --exclude=__pycache__ --exclude='*.pyc' --exclude='.DS_Store' "$SRC" "$DEST" >/dev/null 2>&1; then
    printf '%s\n' "in sync"; exit 0
  fi
  printf '%s\n' "DRIFT between repo and deployed skill:"
  diff -rq --exclude=__pycache__ --exclude='*.pyc' --exclude='.DS_Store' "$SRC" "$DEST" || true
  exit 1
fi

mkdir -p "$DEST"
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' "$SRC/" "$DEST/"
printf '%s\n' "deployed -> $DEST"

# The install fingerprint covers file paths, so a fresh copy reads as stale
# until re-recorded. Skipped automatically when no config exists yet.
if [ -f "$HOME/.config/$NAME/agent-device-env.sh" ]; then
  ( cd "$DEST" && sh scripts/preflight.sh --record )
fi
