from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = SKILL_ROOT / "scripts" / "preflight.sh"

# Variables the config loader exports. `preflight.sh` sources that loader before
# it runs this suite, so a test that inherits them would exercise the caller's
# real toolchain instead of its own fixtures. Scrub them to keep tests hermetic.
LEAKED_ENV_VARS = (
    "AGENT_DEVICE_BIN",
    "AGENT_DEVICE_DEVICE",
    "AGENT_DEVICE_GUARD_BIN",
    "AGENT_DEVICE_NODE_BIN",
    "AGENT_DEVICE_PLATFORM",
    "AGENT_DEVICE_RAW_BIN",
    "AGENT_DEVICE_SERIAL",
    "AGENT_DEVICE_SESSION",
    "ANDROID_HOME",
    "ANDROID_SDK_ROOT",
    "CSI_ADB_BIN",
    "CSI_AGENT_DEVICE_ENV",
    "CSI_APP_BUNDLE_REGISTRY",
    "CSI_INSTALL_STATE",
    "CSI_VIEWPORT_HEIGHT",
    "CSI_VIEWPORT_WIDTH",
    "SCREENSHOT_STITCHER_BIN",
    "SCREENSHOT_STITCHER_HOME",
    "SCREENSHOT_STITCHER_PYTHON",
)


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in LEAKED_ENV_VARS:
        environment.pop(name, None)
    return environment



class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.node_dir = self.root / "node-bin"
        self.agent_dir = self.root / "agent-bin"
        self.android_sdk = self.root / "android-sdk"
        self.adb_bin = self.android_sdk / "platform-tools" / "adb"
        self.stitcher_home = self.root / "screenshot-stitcher"
        self.state_file = self.root / "state" / "install-state.json"
        self.config_file = self.root / "agent-device-env.sh"

        self._write_executable(
            self.node_dir / "node",
            "#!/bin/sh\nprintf '%s\\n' 'v24.14.0'\n",
        )
        self._write_executable(
            self.agent_dir / "agent-device",
            "#!/bin/sh\nprintf '%s\\n' '0.20.0'\n",
        )
        self._write_executable(
            self.adb_bin,
            "#!/bin/sh\nprintf '%s\\n' 'Android Debug Bridge version 1.0.41' 'Version 35.0.2'\n",
        )
        self._write_executable(
            self.stitcher_home / "bin" / "python",
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = '--version' ]; then\n"
            "  printf '%s\\n' 'Python 3.12.13'\n"
            "fi\n"
            "exit 0\n",
        )
        self._write_executable(
            self.stitcher_home / "bin" / "screenshot-stitcher",
            "#!/bin/sh\nprintf '%s\\n' 'usage: screenshot-stitcher'\n",
        )
        self._write_config()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_executable(self, path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _write_config(self) -> None:
        values = {
            "AGENT_DEVICE_NODE_BIN": self.node_dir,
            "AGENT_DEVICE_BIN": self.agent_dir,
            "ANDROID_HOME": self.android_sdk,
            "ANDROID_SDK_ROOT": self.android_sdk,
            "CSI_ADB_BIN": self.adb_bin,
            "SCREENSHOT_STITCHER_HOME": self.stitcher_home,
            "SCREENSHOT_STITCHER_PYTHON": self.stitcher_home / "bin" / "python",
            "SCREENSHOT_STITCHER_BIN": self.stitcher_home / "bin" / "screenshot-stitcher",
            "AGENT_DEVICE_PLATFORM": "android",
            "AGENT_DEVICE_DEVICE": "Fixture Pixel",
            "AGENT_DEVICE_SESSION": "fixture-session",
        }
        lines = [f"export {key}={shlex.quote(str(value))}" for key, value in values.items()]
        self.config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = clean_environment()
        environment.update(
            {
                "CSI_AGENT_DEVICE_ENV": str(self.config_file),
                "CSI_INSTALL_STATE": str(self.state_file),
                "CSI_PREFLIGHT_SKIP_TESTS": "1",
            }
        )
        return subprocess.run(
            ["sh", str(PREFLIGHT), *arguments],
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )

    def test_new_user_is_routed_to_install_then_cached(self) -> None:
        initial = self._run()
        self.assertEqual(10, initial.returncode, initial.stderr)
        initial_payload = json.loads(initial.stdout)
        self.assertEqual("setup_required", initial_payload["status"])
        self.assertIn("install_state_missing", initial_payload["reasons"])
        self.assertEqual("read_install", initial_payload["next_action"])

        recorded = self._run("--record")
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        self.assertEqual(
            {"status": "ready", "cached": False, "recorded": True},
            json.loads(recorded.stdout),
        )
        self.assertTrue(self.state_file.is_file())

        cached = self._run()
        self.assertEqual(0, cached.returncode, cached.stderr)
        self.assertEqual(
            {"status": "ready", "cached": True},
            json.loads(cached.stdout),
        )

    def test_configuration_change_invalidates_marker(self) -> None:
        recorded = self._run("--record")
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        with self.config_file.open("a", encoding="utf-8") as config:
            config.write("# changed\n")

        stale = self._run()
        self.assertEqual(10, stale.returncode, stale.stderr)
        payload = json.loads(stale.stdout)
        self.assertIn("installation_state_stale", payload["reasons"])

    def test_missing_dependency_is_reported_without_state_write(self) -> None:
        (self.agent_dir / "agent-device").unlink()
        result = self._run("--record")
        self.assertEqual(10, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("agent_device_missing", payload["reasons"])
        self.assertFalse(self.state_file.exists())

    def test_missing_adb_is_reported_without_state_write(self) -> None:
        self.adb_bin.unlink()
        result = self._run("--record")
        self.assertEqual(10, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("adb_missing", payload["reasons"])
        self.assertFalse(self.state_file.exists())

    def test_non_android_platform_configuration_is_rejected(self) -> None:
        # A configuration copied from the iOS skill must not silently pass here.
        contents = self.config_file.read_text(encoding="utf-8")
        self.config_file.write_text(
            contents.replace("AGENT_DEVICE_PLATFORM=android", "AGENT_DEVICE_PLATFORM=ios"),
            encoding="utf-8",
        )
        result = self._run("--record")
        self.assertEqual(10, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("android_platform_configuration_missing", payload["reasons"])
        self.assertFalse(self.state_file.exists())


if __name__ == "__main__":
    unittest.main()
