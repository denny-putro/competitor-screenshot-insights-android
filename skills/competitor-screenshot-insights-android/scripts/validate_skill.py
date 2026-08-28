#!/usr/bin/env python3
"""Validate this skill's frontmatter without depending on a global Codex runtime."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        return [f"Missing {skill_path}"]
    text = skill_path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return ["SKILL.md must start with YAML frontmatter"]
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        return [f"Invalid YAML frontmatter: {error}"]
    if not isinstance(frontmatter, dict):
        return ["Frontmatter must be an object"]
    if set(frontmatter) != {"name", "description"}:
        errors.append("Frontmatter must contain only name and description")
    name = frontmatter.get("name")
    if name != root.name:
        errors.append(f"Skill name {name!r} must match folder {root.name!r}")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        errors.append("Skill name must use 1–64 lowercase letters, digits, or hyphens")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("Skill description is required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: skill frontmatter and folder contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
