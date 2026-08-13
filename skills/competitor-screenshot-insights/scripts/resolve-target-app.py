#!/usr/bin/env python3
"""Resolve, discover, and verify named iPhone apps without bundle guessing."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


EXIT_UNMAPPED = 3
EXIT_AMBIGUOUS = 4
EXIT_MISMATCH = 5
EXIT_CONFLICT = 6
DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "references" / "app-bundle-ids.md"


@dataclass(frozen=True)
class AppTarget:
    app: str
    bundle_id: str
    visible_brand: str
    aliases: tuple[str, ...]
    verified: str

    def as_json(self) -> dict[str, Any]:
        return {
            "app": self.app,
            "bundle_id": self.bundle_id,
            "visible_brand": self.visible_brand,
            "aliases": list(self.aliases),
            "verified": self.verified,
        }


@dataclass(frozen=True)
class InstalledApp:
    app: str
    bundle_id: str

    def as_json(self) -> dict[str, str]:
        return {"app": self.app, "bundle_id": self.bundle_id, "visible_brand": self.app}


class RegistryError(ValueError):
    pass


class RegistrationConflict(RegistryError):
    pass


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip()).casefold()


def cell(value: str) -> str:
    return value.strip().strip("`").strip()


def is_divider(values: list[str]) -> bool:
    return bool(values) and all(re.fullmatch(r":?-{3,}:?", item.replace(" ", "")) for item in values)


def parse_registry(path: Path) -> list[AppTarget]:
    if not path.is_file():
        raise RegistryError(f"Registry not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = None
    headers: list[str] = []
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        values = [cell(item) for item in line.strip().strip("|").split("|")]
        if {"App", "Bundle ID", "Visible brand", "Aliases", "Verified"}.issubset(values):
            header_index = index
            headers = values
            break
    if header_index is None:
        raise RegistryError("Registry table must include App, Bundle ID, Visible brand, Aliases, and Verified columns")

    records: list[AppTarget] = []
    for line in lines[header_index + 1 :]:
        if not line.lstrip().startswith("|"):
            if records:
                break
            continue
        values = [cell(item) for item in line.strip().strip("|").split("|")]
        if is_divider(values):
            continue
        if len(values) != len(headers):
            raise RegistryError(f"Malformed registry row: {line}")
        record = dict(zip(headers, values))
        aliases = tuple(alias.strip() for alias in record["Aliases"].split(";") if alias.strip() and alias.strip() != "—")
        target = AppTarget(
            app=record["App"],
            bundle_id=record["Bundle ID"],
            visible_brand=record["Visible brand"],
            aliases=aliases,
            verified=record["Verified"],
        )
        if not all((target.app, target.bundle_id, target.visible_brand, target.verified)):
            raise RegistryError(f"Registry row has a required empty field: {line}")
        records.append(target)
    if not records:
        raise RegistryError("Registry has no app records")
    validate_records(records)
    return records


def validate_records(records: list[AppTarget]) -> None:
    identities: dict[str, str] = {}
    bundles: dict[str, str] = {}
    for target in records:
        if target.bundle_id in bundles:
            raise RegistryError(f"Duplicate bundle ID {target.bundle_id!r} for {target.app!r} and {bundles[target.bundle_id]!r}")
        bundles[target.bundle_id] = target.app
        for identity in (target.app, *target.aliases):
            normalized = normalize(identity)
            if not normalized:
                raise RegistryError(f"Empty identity for {target.app!r}")
            if normalized in identities and identities[normalized] != target.app:
                raise RegistryError(f"Ambiguous app identity {identity!r} for {target.app!r} and {identities[normalized]!r}")
            identities[normalized] = target.app


def target_matches(app: str, records: list[AppTarget]) -> list[AppTarget]:
    query = normalize(app)
    return [target for target in records if query in {normalize(target.app), *(normalize(alias) for alias in target.aliases)}]


def resolve(app: str, registry: Path) -> AppTarget:
    matches = target_matches(app, parse_registry(registry))
    if not matches:
        emit({"status": "unmapped", "requested_app": app, "registry": str(registry.resolve())})
        raise SystemExit(EXIT_UNMAPPED)
    if len(matches) != 1:
        emit({"status": "ambiguous", "requested_app": app, "candidates": [target.as_json() for target in matches]})
        raise SystemExit(EXIT_AMBIGUOUS)
    return matches[0]


def inventory_item(raw: Any) -> InstalledApp:
    if isinstance(raw, str):
        match = re.fullmatch(r"(.+?) \(([^()]+)\)", raw.strip())
        if not match:
            raise RegistryError(f"Malformed installed-app entry: {raw!r}")
        app, bundle_id = match.groups()
    elif isinstance(raw, dict):
        app = raw.get("app", raw.get("name"))
        bundle_id = raw.get("bundle_id", raw.get("bundleId"))
        if not isinstance(app, str) or not isinstance(bundle_id, str):
            raise RegistryError("Installed-app object must contain string app/name and bundle_id/bundleId")
    else:
        raise RegistryError("Installed-app entry must be a string or object")
    if not app.strip() or not bundle_id.strip():
        raise RegistryError("Installed-app entry has an empty app name or bundle ID")
    return InstalledApp(app=app.strip(), bundle_id=bundle_id.strip())


def parse_inventory(path: Path) -> list[InstalledApp]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"Unreadable installed-app inventory: {error}") from error
    raw_apps = payload.get("data", {}).get("apps") if isinstance(payload, dict) else None
    if not isinstance(raw_apps, list):
        raise RegistryError("Installed-app inventory must contain data.apps as a list")
    installed: list[InstalledApp] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_apps:
        candidate = inventory_item(raw)
        key = (normalize(candidate.app), candidate.bundle_id)
        if key not in seen:
            installed.append(candidate)
            seen.add(key)
    return installed


def discover(app: str, registry: Path, inventory: Path) -> InstalledApp:
    registered = target_matches(app, parse_registry(registry))
    if registered:
        emit({"status": "already_registered", "requested_app": app, "target": registered[0].as_json(), "registry": str(registry.resolve())})
        raise SystemExit(EXIT_CONFLICT)
    matches = [candidate for candidate in parse_inventory(inventory) if normalize(candidate.app) == normalize(app)]
    if not matches:
        emit({"status": "not_installed", "requested_app": app, "inventory": str(inventory.resolve())})
        raise SystemExit(EXIT_UNMAPPED)
    if len(matches) != 1:
        emit({"status": "ambiguous_installed_app", "requested_app": app, "candidates": [candidate.as_json() for candidate in matches]})
        raise SystemExit(EXIT_AMBIGUOUS)
    return matches[0]


def application_label(snapshot_path: Path) -> str:
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"Unreadable snapshot: {error}") from error
    for node in payload.get("data", {}).get("nodes", []):
        if node.get("type") == "Application" and isinstance(node.get("label"), str):
            return node["label"]
    raise RegistryError("Snapshot has no Application label")


def foreground_bundle(appstate_path: Path) -> str:
    try:
        text = appstate_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RegistryError(f"Unreadable app state: {error}") from error
    match = re.search(r"^Bundle:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not match:
        raise RegistryError("App state has no foreground bundle")
    return match.group(1)


def require_absolute(path: str, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise RegistryError(f"{label} must be an absolute path")
    return candidate


def verify_observed(target: AppTarget, args: argparse.Namespace) -> tuple[Path, Path, str, str] | None:
    screenshot = require_absolute(args.screenshot, "Screenshot path")
    manifest = require_absolute(args.manifest, "Manifest path")
    if not screenshot.is_file():
        raise RegistryError(f"Screenshot not found: {screenshot}")
    foreground = foreground_bundle(Path(args.appstate))
    observed_brand = application_label(Path(args.snapshot))
    mismatch: dict[str, Any] = {}
    if foreground != target.bundle_id:
        mismatch["foreground_bundle"] = {"expected": target.bundle_id, "observed": foreground}
    if normalize(observed_brand) != normalize(target.visible_brand):
        mismatch["visible_brand"] = {"expected": target.visible_brand, "observed": observed_brand}
    if mismatch:
        emit({"status": "identity_mismatch", "requested_app": args.app, "target": target.as_json(), "mismatch": mismatch})
        return None
    return screenshot, manifest, foreground, observed_brand


def write_manifest(
    manifest: Path,
    screenshot: Path,
    requested_app: str,
    target: AppTarget,
    foreground: str,
    observed_brand: str,
    registry: Path,
    source: str,
) -> None:
    payload = {
        "schema_version": 1,
        "status": "verified",
        "source": source,
        "requested_app": requested_app,
        "target": target.as_json(),
        "observed": {"foreground_bundle": foreground, "application_label": observed_brand},
        "evidence": {"launch_screenshot": str(screenshot)},
        "registry": str(registry.resolve()),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_table_cell(value: str, label: str) -> str:
    if not value.strip() or "|" in value or "\n" in value or "\r" in value:
        raise RegistryError(f"Discovered {label} cannot be safely written to the registry")
    return value.strip()


def append_discovered_target(registry: Path, target: AppTarget) -> None:
    records = parse_registry(registry)
    for existing in records:
        if existing.bundle_id == target.bundle_id:
            raise RegistrationConflict(f"Bundle ID {target.bundle_id!r} is already registered to {existing.app!r}")
        if normalize(target.app) in {normalize(existing.app), *(normalize(alias) for alias in existing.aliases)}:
            raise RegistrationConflict(f"App name {target.app!r} is already registered to {existing.app!r}")

    app = safe_table_cell(target.app, "app name")
    bundle_id = safe_table_cell(target.bundle_id, "bundle ID")
    visible_brand = safe_table_cell(target.visible_brand, "visible brand")
    verified = safe_table_cell(target.verified, "verification date")
    row = f"| {app} | `{bundle_id}` | {visible_brand} | — | {verified} |"

    lines = registry.read_text(encoding="utf-8").splitlines()
    header_index = next(
        index
        for index, line in enumerate(lines)
        if line.lstrip().startswith("|")
        and {"App", "Bundle ID", "Visible brand", "Aliases", "Verified"}.issubset(
            [cell(item) for item in line.strip().strip("|").split("|")]
        )
    )
    insert_at = header_index + 2
    for index in range(header_index + 2, len(lines)):
        if lines[index].lstrip().startswith("|"):
            insert_at = index + 1
        else:
            break
    lines.insert(insert_at, row)
    registry.write_text("\n".join(lines) + "\n", encoding="utf-8")


def discovered_target(candidate: InstalledApp) -> AppTarget:
    return AppTarget(
        app=candidate.app,
        bundle_id=candidate.bundle_id,
        visible_brand=candidate.app,
        aliases=(),
        verified=date.today().isoformat(),
    )


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def command_resolve(args: argparse.Namespace) -> int:
    target = resolve(args.app, args.registry)
    emit({"status": "resolved", "requested_app": args.app, "target": target.as_json(), "registry": str(args.registry.resolve())})
    return 0


def command_discover(args: argparse.Namespace) -> int:
    candidate = discover(args.app, args.registry, Path(args.inventory))
    emit({"status": "discovered", "requested_app": args.app, "candidate": candidate.as_json(), "inventory": str(Path(args.inventory).resolve())})
    return 0


def command_validate(args: argparse.Namespace) -> int:
    targets = parse_registry(args.registry)
    emit({"status": "valid", "registry": str(args.registry.resolve()), "count": len(targets)})
    return 0


def command_verify(args: argparse.Namespace) -> int:
    target = resolve(args.app, args.registry)
    observed = verify_observed(target, args)
    if observed is None:
        return EXIT_MISMATCH
    screenshot, manifest, foreground, observed_brand = observed
    write_manifest(manifest, screenshot, args.app, target, foreground, observed_brand, args.registry, "registry")
    emit({"status": "verified", "manifest": str(manifest), "target": target.as_json()})
    return 0


def command_register_discovered(args: argparse.Namespace) -> int:
    candidate = discover(args.app, args.registry, Path(args.inventory))
    target = discovered_target(candidate)
    observed = verify_observed(target, args)
    if observed is None:
        return EXIT_MISMATCH
    screenshot, manifest, foreground, observed_brand = observed
    append_discovered_target(args.registry, target)
    write_manifest(manifest, screenshot, args.app, target, foreground, observed_brand, args.registry, "auto_discovered")
    emit({"status": "registered", "manifest": str(manifest), "target": target.as_json(), "registry": str(args.registry.resolve())})
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("resolve", "verify", "discover", "register-discovered"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--app", required=True)
    subparsers.add_parser("validate")
    for name in ("discover", "register-discovered"):
        subparsers.choices[name].add_argument("--inventory", required=True)
    for name in ("verify", "register-discovered"):
        verifier = subparsers.choices[name]
        verifier.add_argument("--appstate", required=True)
        verifier.add_argument("--snapshot", required=True)
        verifier.add_argument("--screenshot", required=True)
        verifier.add_argument("--manifest", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "resolve":
            return command_resolve(args)
        if args.command == "discover":
            return command_discover(args)
        if args.command == "validate":
            return command_validate(args)
        if args.command == "verify":
            return command_verify(args)
        return command_register_discovered(args)
    except RegistrationConflict as error:
        emit({"status": "registration_conflict", "error": str(error)})
        return EXIT_CONFLICT
    except RegistryError as error:
        emit({"status": "invalid_registry_or_inventory_or_evidence", "error": str(error)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
