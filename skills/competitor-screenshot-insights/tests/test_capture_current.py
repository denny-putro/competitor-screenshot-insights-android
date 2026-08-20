from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "capture_current.py"
SPEC = importlib.util.spec_from_file_location("capture_current", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReadinessTests(unittest.TestCase):
    def test_readiness_marker_is_scoped_to_session_and_device(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "ready.json"
            with mock.patch.dict(os.environ, {"AGENT_DEVICE_DEVICE": "fixture-phone"}):
                MODULE.record_readiness(marker, "session-a")
                self.assertTrue(MODULE.readiness_is_fresh(marker, "session-a"))
                self.assertFalse(MODULE.readiness_is_fresh(marker, "session-b"))
            payload = json.loads(marker.read_text(encoding="utf-8"))
            self.assertNotIn("fixture-phone", marker.read_text(encoding="utf-8"))
            self.assertEqual(64, len(payload["readiness_key"]))

    def test_stale_readiness_marker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "ready.json"
            with mock.patch.dict(os.environ, {"AGENT_DEVICE_DEVICE": "fixture-phone"}):
                MODULE.record_readiness(marker, "session-a")
                payload = json.loads(marker.read_text(encoding="utf-8"))
                now = float(payload["checked_at_epoch"]) + MODULE.READY_TTL_SECONDS + 1
                self.assertFalse(MODULE.readiness_is_fresh(marker, "session-a", now=now))


class CaptureConstructionTests(unittest.TestCase):
    def run_capture(self, mode: str) -> tuple[dict, list[list[str]]]:
        commands: list[list[str]] = []

        def fake_recovery(command, label, **kwargs):
            commands.append(command)
            if "screenshot" in command:
                Path(command[command.index("screenshot") + 1]).write_bytes(b"fixture")
            return subprocess.CompletedProcess(command, 0, "{}", "")

        def fake_run(command, label, **kwargs):
            commands.append(command)
            if any(part.endswith("check-viewport.sh") for part in command):
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps({"decision": "accept", "dimensions": {"width": 1, "height": 1}}),
                    "",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "decision": "accept",
                        "captured_viewports": 3.5,
                        "page_complete": mode == "full",
                        "stop_reason": "page_bottom_reached" if mode == "full" else "soft_viewport_limit_reached",
                    }
                ),
                "",
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "result.png"
            with (
                mock.patch.object(MODULE, "run_with_warm_recovery", side_effect=fake_recovery),
                mock.patch.object(MODULE, "run_command", side_effect=fake_run),
                mock.patch.object(MODULE, "foreground_bundle", return_value="com.example.app"),
            ):
                payload = MODULE.capture_long(
                    MODULE_PATH.parent,
                    output,
                    "fixture-session",
                    mode,
                    True,
                    90.0,
                    root / "work",
                )
        return payload, commands

    def test_long_starts_at_current_position_with_auto_extent(self) -> None:
        payload, commands = self.run_capture("long")
        pipeline = next(
            command
            for command in commands
            if any(part.endswith("capture-long-fast.sh") for part in command)
        )
        self.assertIn("--allow-current-position", pipeline)
        self.assertEqual("auto", pipeline[pipeline.index("--capture-extent") + 1])
        self.assertEqual("long", payload["mode"])

    def test_full_scrolls_to_top_and_requests_full_extent(self) -> None:
        payload, commands = self.run_capture("full")
        self.assertIn(
            ["agent-device", "scroll", "top", "--session", "fixture-session", "--json"],
            commands,
        )
        pipeline = next(
            command
            for command in commands
            if any(part.endswith("capture-long-fast.sh") for part in command)
        )
        self.assertNotIn("--allow-current-position", pipeline)
        self.assertEqual("full", pipeline[pipeline.index("--capture-extent") + 1])
        self.assertEqual("full", payload["mode"])


if __name__ == "__main__":
    unittest.main()
