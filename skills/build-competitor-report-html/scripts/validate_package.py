#!/usr/bin/env python3
"""Validate the self-contained report Skill package without third-party dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/content-quality-gate.md",
    "references/evidence-organization.md",
    "references/component-registry.yaml",
    "references/publishing-metadata.json",
    "references/components/typography.md",
    "references/components/report-hero.md",
    "references/components/report-navigation.md",
    "references/components/test-criteria.md",
    "references/components/screenshot-viewer.md",
    "assets/components/report-foundation.css",
    "assets/components/report-hero.css",
    "assets/components/report-hero.js",
    "assets/components/hero-reference.html",
    "assets/components/report-navigation.css",
    "assets/components/report-navigation.js",
    "assets/components/test-criteria.css",
    "assets/components/screenshot-viewer.css",
    "assets/components/screenshot-viewer.js",
)


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


for relative_path in REQUIRED_FILES:
    path = SKILL_ROOT / relative_path
    if not path.is_file() or path.stat().st_size == 0:
        fail(f"missing or empty required file: {relative_path}")

skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
registry_text = (SKILL_ROOT / "references/component-registry.yaml").read_text(
    encoding="utf-8"
)
metadata_text = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")

if not skill_text.startswith("---\nname: build-competitor-report-html\ndescription:"):
    fail("SKILL.md frontmatter name or description is invalid")

for forbidden in ("provider_skill:", "../publish-web", "~/.codex/skills"):
    if forbidden in skill_text or forbidden in registry_text:
        fail(f"external Skill dependency remains: {forbidden}")

if "$build-competitor-report-html" not in metadata_text:
    fail("agents/openai.yaml default_prompt must mention the Skill by name")

registered_paths = set(
    re.findall(r"(?:reference:|^\s+-)\s+(references/\S+|assets/\S+)$", registry_text, re.M)
)
expected_registered_paths = {
    path for path in REQUIRED_FILES if path.startswith(("references/components/", "assets/"))
}
if registered_paths != expected_registered_paths:
    missing = sorted(expected_registered_paths - registered_paths)
    extra = sorted(registered_paths - expected_registered_paths)
    fail(f"component registry mismatch; missing={missing}, extra={extra}")

print("PASS: self-contained report Skill package")
