from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup.sh"
PREFLIGHT = ROOT / "scripts" / "preflight.sh"


class SetupTests(unittest.TestCase):
    def _write_executable(self, path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def test_setup_writes_private_sourceable_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node_bin = root / "node"
            agent_bin = root / "agent"
            xcode = root / "Xcode Test.app"
            developer = xcode / "Contents" / "Developer"
            stitcher = root / "stitcher"
            config = root / "private" / "agent-device-env.sh"
            state = root / "state" / "install.json"

            self._write_executable(node_bin / "node", "#!/bin/sh\nprintf '%s\\n' 'v24.0.0'\n")
            self._write_executable(agent_bin / "agent-device", "#!/bin/sh\nprintf '%s\\n' '0.20.8'\n")
            self._write_executable(developer / "usr" / "bin" / "xcodebuild", "#!/bin/sh\nprintf '%s\\n' 'Xcode 26.0'\n")
            self._write_executable(developer / "usr" / "bin" / "xcrun", "#!/bin/sh\nprintf '%s\\n' '26.0'\n")
            self._write_executable(
                stitcher / "bin" / "python",
                "#!/bin/sh\nif [ \"${1:-}\" = '--version' ]; then printf '%s\\n' 'Python 3.12.0'; fi\nexit 0\n",
            )
            self._write_executable(stitcher / "bin" / "screenshot-stitcher", "#!/bin/sh\nprintf '%s\\n' 'usage'\n")

            result = subprocess.run(
                [
                    "sh",
                    str(SETUP),
                    "--device",
                    "Tester's iPhone",
                    "--team-id",
                    "TESTTEAM",
                    "--bundle-id",
                    "dev.example.runner",
                    "--node-bin",
                    str(node_bin),
                    "--agent-device-bin",
                    str(agent_bin),
                    "--xcode",
                    str(xcode),
                    "--stitcher-home",
                    str(stitcher),
                    "--viewport-width",
                    "393",
                    "--viewport-height",
                    "852",
                    "--config",
                    str(config),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("configured", json.loads(result.stdout)["status"])
            self.assertEqual(0o600, stat.S_IMODE(config.stat().st_mode))

            loaded = subprocess.run(
                [
                    "sh",
                    "-c",
                    '. "$1"; printf "%s|%s|%s" "$AGENT_DEVICE_DEVICE" "$CSI_VIEWPORT_WIDTH" "$CSI_VIEWPORT_HEIGHT"',
                    "sh",
                    str(config),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, loaded.returncode, loaded.stderr)
            self.assertEqual("Tester's iPhone|393|852", loaded.stdout)

            environment = os.environ.copy()
            environment.update(
                {
                    "CSI_AGENT_DEVICE_ENV": str(config),
                    "CSI_INSTALL_STATE": str(state),
                    "CSI_PREFLIGHT_SKIP_TESTS": "1",
                }
            )
            recorded = subprocess.run(
                ["sh", str(PREFLIGHT), "--record"],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )
            self.assertEqual(0, recorded.returncode, f"stdout={recorded.stdout}\nstderr={recorded.stderr}")
            self.assertTrue(state.is_file())


if __name__ == "__main__":
    unittest.main()
