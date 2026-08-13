from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve-target-app.py"
OPENER = ROOT / "scripts" / "open-mapped-app.sh"
REGISTRY = ROOT / "references" / "app-bundle-ids.md"


def run_with_registry(registry: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(SCRIPT), "--registry", str(registry), *args], text=True, capture_output=True, check=False)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return run_with_registry(REGISTRY, *args)


def write_inventory(path: Path, *apps: str) -> None:
    path.write_text(json.dumps({"success": True, "data": {"apps": list(apps)}}), encoding="utf-8")


def write_executable(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def fake_device_environment(root: Path, apps: tuple[str, ...], bundle_id: str, visible_brand: str) -> tuple[dict[str, str], Path]:
    raw_cli = root / "fake-agent-device"
    guard_dir = root / "guard-bin"
    guard_cli = guard_dir / "agent-device"
    command_log = root / "commands.log"
    inventory = shlex.quote(json.dumps({"success": True, "data": {"apps": list(apps)}}))
    appstate = shlex.quote(f"Bundle: {bundle_id}\n")
    snapshot = shlex.quote(json.dumps({"data": {"nodes": [{"type": "Application", "label": visible_brand}]}}))
    write_executable(
        raw_cli,
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"${1:-}\" >> \"$FAKE_COMMAND_LOG\"\n"
        "case \"${1:-}\" in\n"
        f"  apps) printf '%s\\n' {inventory} ;;\n"
        "  open) printf 'Opened: %s\\n' \"${2:-}\" ;;\n"
        "  wait) : ;;\n"
        "  screenshot) : > \"${2:?missing screenshot path}\" ;;\n"
        f"  appstate) printf '%s' {appstate} ;;\n"
        f"  snapshot) printf '%s' {snapshot} ;;\n"
        "  *) printf 'unexpected command: %s\\n' \"${1:-}\" >&2; exit 2 ;;\n"
        "esac\n",
    )
    write_executable(
        guard_cli,
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"${1:-}\" = open ]; then exit 64; fi\n"
        "exec \"$AGENT_DEVICE_RAW_BIN\" \"$@\"\n",
    )
    config = root / "agent-device-env.sh"
    config.write_text(
        f"AGENT_DEVICE_RAW_BIN={shlex.quote(str(raw_cli))}\n"
        f"PATH={shlex.quote(str(guard_dir))}:$PATH\n"
        "export AGENT_DEVICE_RAW_BIN PATH\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.update({"CSI_AGENT_DEVICE_ENV": str(config), "FAKE_COMMAND_LOG": str(command_log)})
    return environment, command_log


class ResolveTargetAppTests(unittest.TestCase):
    def test_registry_validates(self) -> None:
        result = run("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "valid")

    def test_canonical_and_aliases_resolve_to_distinct_ctrip_targets(self) -> None:
        ctrip = run("resolve", "--app", "携程")
        trip = run("resolve", "--app", "Trip.com")
        self.assertEqual(ctrip.returncode, 0, ctrip.stderr)
        self.assertEqual(trip.returncode, 0, trip.stderr)
        self.assertEqual(json.loads(ctrip.stdout)["target"]["bundle_id"], "ctrip.com")
        self.assertEqual(json.loads(trip.stdout)["target"]["bundle_id"], "com.ctrip.EBooking")

    def test_unmapped_target_fails_closed(self) -> None:
        result = run("resolve", "--app", "Unknown travel app")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["status"], "unmapped")

    def test_discovery_accepts_only_one_exact_installed_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "apps.json"
            write_inventory(inventory, "Fresh App (com.example.fresh)", "Fresh App Pro (com.example.pro)")
            result = run("discover", "--app", "Fresh App", "--inventory", str(inventory))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("discovered", payload["status"])
            self.assertEqual(
                {"app": "Fresh App", "bundle_id": "com.example.fresh", "visible_brand": "Fresh App"},
                payload["candidate"],
            )

    def test_discovery_rejects_non_exact_or_duplicate_installed_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            non_exact_inventory = root / "non-exact.json"
            duplicate_inventory = root / "duplicate.json"
            write_inventory(non_exact_inventory, "Fresh App Pro (com.example.pro)")
            write_inventory(duplicate_inventory, "Fresh App (com.example.one)", "Fresh App (com.example.two)")
            non_exact = run("discover", "--app", "Fresh App", "--inventory", str(non_exact_inventory))
            duplicate = run("discover", "--app", "Fresh App", "--inventory", str(duplicate_inventory))
            self.assertEqual(3, non_exact.returncode)
            self.assertEqual("not_installed", json.loads(non_exact.stdout)["status"])
            self.assertEqual(4, duplicate.returncode)
            self.assertEqual("ambiguous_installed_app", json.loads(duplicate.stdout)["status"])

    def test_verify_requires_matching_bundle_and_visible_brand(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "launch.png"
            appstate = root / "appstate.txt"
            snapshot = root / "snapshot.json"
            manifest = root / "nested" / "target.json"
            screenshot.write_bytes(b"png")
            appstate.write_text("Foreground app: ctrip.com\nBundle: ctrip.com\n", encoding="utf-8")
            snapshot.write_text(json.dumps({"data": {"nodes": [{"type": "Application", "label": "携程旅行"}]}}), encoding="utf-8")
            result = run(
                "verify",
                "--app",
                "携程旅行",
                "--appstate",
                str(appstate),
                "--snapshot",
                str(snapshot),
                "--screenshot",
                str(screenshot),
                "--manifest",
                str(manifest),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(manifest.is_file())
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["observed"]["application_label"], "携程旅行")

    def test_verify_fails_on_brand_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "launch.png"
            appstate = root / "appstate.txt"
            snapshot = root / "snapshot.json"
            manifest = root / "target.json"
            screenshot.write_bytes(b"png")
            appstate.write_text("Bundle: ctrip.com\n", encoding="utf-8")
            snapshot.write_text(json.dumps({"data": {"nodes": [{"type": "Application", "label": "Trip.com"}]}}), encoding="utf-8")
            result = run(
                "verify",
                "--app",
                "携程旅行",
                "--appstate",
                str(appstate),
                "--snapshot",
                str(snapshot),
                "--screenshot",
                str(screenshot),
                "--manifest",
                str(manifest),
            )
            self.assertEqual(result.returncode, 5)
            self.assertFalse(manifest.exists())
            self.assertEqual(json.loads(result.stdout)["status"], "identity_mismatch")

    def test_verified_discovery_registers_new_mapping_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry.md"
            registry.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
            inventory = root / "apps.json"
            screenshot = root / "launch.png"
            appstate = root / "appstate.txt"
            snapshot = root / "snapshot.json"
            manifest = root / "nested" / "target.json"
            write_inventory(inventory, "Fresh App (com.example.fresh)")
            screenshot.write_bytes(b"png")
            appstate.write_text("Bundle: com.example.fresh\n", encoding="utf-8")
            snapshot.write_text(json.dumps({"data": {"nodes": [{"type": "Application", "label": "Fresh App"}]}}), encoding="utf-8")
            result = run_with_registry(
                registry,
                "register-discovered",
                "--app",
                "Fresh App",
                "--inventory",
                str(inventory),
                "--appstate",
                str(appstate),
                "--snapshot",
                str(snapshot),
                "--screenshot",
                str(screenshot),
                "--manifest",
                str(manifest),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual("registered", json.loads(result.stdout.strip().splitlines()[-1])["status"])
            resolved = run_with_registry(registry, "resolve", "--app", "Fresh App")
            self.assertEqual(0, resolved.returncode, resolved.stderr)
            self.assertEqual("com.example.fresh", json.loads(resolved.stdout)["target"]["bundle_id"])
            self.assertEqual("auto_discovered", json.loads(manifest.read_text(encoding="utf-8"))["source"])

    def test_failed_discovery_verification_cannot_register_a_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry.md"
            initial_registry = REGISTRY.read_text(encoding="utf-8")
            registry.write_text(initial_registry, encoding="utf-8")
            inventory = root / "apps.json"
            screenshot = root / "launch.png"
            appstate = root / "appstate.txt"
            snapshot = root / "snapshot.json"
            manifest = root / "target.json"
            write_inventory(inventory, "Fresh App (com.example.fresh)")
            screenshot.write_bytes(b"png")
            appstate.write_text("Bundle: com.example.fresh\n", encoding="utf-8")
            snapshot.write_text(json.dumps({"data": {"nodes": [{"type": "Application", "label": "Other App"}]}}), encoding="utf-8")
            result = run_with_registry(
                registry,
                "register-discovered",
                "--app",
                "Fresh App",
                "--inventory",
                str(inventory),
                "--appstate",
                str(appstate),
                "--snapshot",
                str(snapshot),
                "--screenshot",
                str(screenshot),
                "--manifest",
                str(manifest),
            )
            self.assertEqual(5, result.returncode)
            self.assertEqual("identity_mismatch", json.loads(result.stdout)["status"])
            self.assertEqual(initial_registry, registry.read_text(encoding="utf-8"))
            self.assertFalse(manifest.exists())

    def test_opener_auto_discovers_and_registers_without_a_manual_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry.md"
            registry.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
            environment, command_log = fake_device_environment(
                root,
                ("Fresh Device App (com.example.device)",),
                "com.example.device",
                "Fresh Device App",
            )
            screenshot = root / "launch.png"
            manifest = root / "target.json"
            result = subprocess.run(
                [
                    str(OPENER),
                    "--registry",
                    str(registry),
                    "--app",
                    "Fresh Device App",
                    "--screenshot",
                    str(screenshot),
                    "--manifest",
                    str(manifest),
                ],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )
            self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
            self.assertEqual("registered", json.loads(result.stdout.strip().splitlines()[-1])["status"])
            self.assertEqual(["apps", "open", "wait", "screenshot", "appstate", "snapshot"], command_log.read_text(encoding="utf-8").splitlines())
            self.assertEqual("com.example.device", json.loads(run_with_registry(registry, "resolve", "--app", "Fresh Device App").stdout)["target"]["bundle_id"])
            self.assertEqual("auto_discovered", json.loads(manifest.read_text(encoding="utf-8"))["source"])

    def test_opener_seeds_private_registry_when_no_registry_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, command_log = fake_device_environment(
                root,
                ("Fresh Private App (com.example.private)",),
                "com.example.private",
                "Fresh Private App",
            )
            private_config = root / "config"
            environment["XDG_CONFIG_HOME"] = str(private_config)
            screenshot = root / "launch.png"
            manifest = root / "target.json"
            result = subprocess.run(
                [
                    str(OPENER),
                    "--app",
                    "Fresh Private App",
                    "--screenshot",
                    str(screenshot),
                    "--manifest",
                    str(manifest),
                ],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )
            self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
            registry = private_config / "competitor-screenshot-insights" / "app-bundle-ids.md"
            self.assertTrue(registry.is_file())
            self.assertIn("Fresh Private App", registry.read_text(encoding="utf-8"))
            self.assertEqual(["apps", "open", "wait", "screenshot", "appstate", "snapshot"], command_log.read_text(encoding="utf-8").splitlines())

    def test_opener_rejects_ambiguous_inventory_without_opening_any_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry.md"
            initial_registry = REGISTRY.read_text(encoding="utf-8")
            registry.write_text(initial_registry, encoding="utf-8")
            environment, command_log = fake_device_environment(
                root,
                ("Fresh Device App (com.example.one)", "Fresh Device App (com.example.two)"),
                "com.example.one",
                "Fresh Device App",
            )
            screenshot = root / "launch.png"
            manifest = root / "target.json"
            result = subprocess.run(
                [
                    str(OPENER),
                    "--registry",
                    str(registry),
                    "--app",
                    "Fresh Device App",
                    "--screenshot",
                    str(screenshot),
                    "--manifest",
                    str(manifest),
                ],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )
            self.assertEqual(4, result.returncode, result.stderr)
            self.assertIn('"status": "ambiguous_installed_app"', result.stderr)
            self.assertEqual(["apps"], command_log.read_text(encoding="utf-8").splitlines())
            self.assertEqual(initial_registry, registry.read_text(encoding="utf-8"))
            self.assertFalse(screenshot.exists())
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
