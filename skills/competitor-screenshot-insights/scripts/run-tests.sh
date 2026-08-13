#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

BASE_PYTHON=
if [ -n "${CSI_EVAL_PYTHON:-}" ]; then
  BASE_PYTHON=$CSI_EVAL_PYTHON
else
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      candidate_path=$(command -v "$candidate")
      if "$candidate_path" -c 'import sys; raise SystemExit(0 if (3, 12) <= sys.version_info < (4, 0) else 1)' >/dev/null 2>&1; then
        BASE_PYTHON=$candidate_path
        break
      fi
    fi
  done
fi

if [ -z "$BASE_PYTHON" ] || [ ! -x "$BASE_PYTHON" ]; then
  echo "Python 3.12 or newer is required to run the Skill tests." >&2
  exit 2
fi

if "$BASE_PYTHON" -c 'import cv2, numpy, yaml' >/dev/null 2>&1; then
  EVAL_PYTHON=$BASE_PYTHON
else
  EVAL_CACHE_ROOT=${CSI_EVAL_CACHE_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/codex/competitor-screenshot-insights-eval}
  EVAL_PYTHON="$EVAL_CACHE_ROOT/bin/python"
  if [ ! -x "$EVAL_PYTHON" ]; then
    mkdir -p "$(dirname -- "$EVAL_CACHE_ROOT")"
    "$BASE_PYTHON" -m venv "$EVAL_CACHE_ROOT"
  fi
  if ! "$EVAL_PYTHON" -c 'import cv2, numpy, yaml' >/dev/null 2>&1; then
    "$EVAL_PYTHON" -m pip install --disable-pip-version-check -r "$SKILL_ROOT/requirements-eval.txt"
  fi
fi

if ! "$EVAL_PYTHON" -c 'import cv2, numpy, yaml' >/dev/null 2>&1; then
  echo "Missing pinned eval dependencies after bootstrap. Set CSI_EVAL_PYTHON to a compatible isolated Python." >&2
  exit 2
fi

"$EVAL_PYTHON" "$SCRIPT_DIR/validate_skill.py" "$SKILL_ROOT"
"$EVAL_PYTHON" -m compileall -q "$SKILL_ROOT/scripts" "$SKILL_ROOT/tests"
"$EVAL_PYTHON" -m unittest discover -s "$SKILL_ROOT/tests" -v

for script in "$SKILL_ROOT"/scripts/*.sh; do
  sh -n "$script"
done

printf 'PASS: candidate skill validation, compile, unit tests, and shell syntax\n'
