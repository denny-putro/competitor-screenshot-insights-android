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


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.node_dir = self.root / "node-bin"
        self.agent_dir = self.root / "agent-bin"
        self.xcode_app = self.root / "Xcode.app"
        self.developer_dir = self.xcode_app / "Contents" / "Developer"
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
            self.developer_dir / "usr" / "bin" / "xcodebuild",
            "#!/bin/sh\nprintf '%s\\n' 'Xcode 26.6' 'Build version TEST'\n",
        )
        self._write_executable(
            self.developer_dir / "usr" / "bin" / "xcrun",
            "#!/bin/sh\nprintf '%s\\n' '26.5'\n",
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
            "AGENT_DEVICE_XCODE_APP": self.xcode_app,
            "DEVELOPER_DIR": self.developer_dir,
            "SCREENSHOT_STITCHER_HOME": self.stitcher_home,
            "SCREENSHOT_STITCHER_PYTHON": self.stitcher_home / "bin" / "python",
            "SCREENSHOT_STITCHER_BIN": self.stitcher_home / "bin" / "screenshot-stitcher",
            "AGENT_DEVICE_PLATFORM": "ios",
            "AGENT_DEVICE_DEVICE": "Fixture iPhone",
            "AGENT_DEVICE_IOS_TEAM_ID": "FIXTURETEAM",
            "AGENT_DEVICE_IOS_BUNDLE_ID": "dev.fixture.runner",
            "AGENT_DEVICE_SESSION": "fixture-session",
        }
        lines = [f"export {key}={shlex.quote(str(value))}" for key, value in values.items()]
        self.config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
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


if __name__ == "__main__":
    unittest.main()
