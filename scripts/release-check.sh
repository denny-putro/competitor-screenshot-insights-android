#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SKILL_ROOT="$REPO_ROOT/skills/competitor-screenshot-insights"

for required in \
  "$REPO_ROOT/LICENSE" \
  "$REPO_ROOT/README.md" \
  "$SKILL_ROOT/SKILL.md" \
  "$SKILL_ROOT/INSTALL.md" \
  "$SKILL_ROOT/scripts/preflight.sh" \
  "$SKILL_ROOT/scripts/setup.sh"
do
  if [ ! -f "$required" ]; then
    printf 'Missing required release file: %s\n' "$required" >&2
    exit 1
  fi
done

if git -C "$REPO_ROOT" ls-files | grep -E '(^|/)(__pycache__/|\.DS_Store$|[^/]+\.pyc$)'; then
  printf '%s\n' 'Generated cache or metadata files are tracked.' >&2
  exit 1
fi

if rg -n --hidden \
  --glob '!.git/**' \
  --glob '!scripts/release-check.sh' \
  '(/Users/|com\.fengjunnan|9FQYYJMFS8|gh[opusr]_[A-Za-z0-9_]{20,})' \
  "$REPO_ROOT"
then
  printf '%s\n' 'Possible private path, signing value, or token detected.' >&2
  exit 1
fi

for executable in \
  "$REPO_ROOT/scripts/release-check.sh" \
  "$SKILL_ROOT/scripts/preflight.sh" \
  "$SKILL_ROOT/scripts/setup.sh" \
  "$SKILL_ROOT/scripts/open-mapped-app.sh"
do
  if [ ! -x "$executable" ]; then
    printf 'Expected executable bit: %s\n' "$executable" >&2
    exit 1
  fi
done

printf '%s\n' 'PASS: release files, privacy scan, and executable contract'
