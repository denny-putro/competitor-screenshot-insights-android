from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fast_capture_mode.py"
WRAPPER_PATH = MODULE_PATH.with_name("fast-capture-mode.sh")
SPEC = importlib.util.spec_from_file_location("fast_capture_mode", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FastCaptureRoutingTests(unittest.TestCase):
    def active_state(self, now: float = 1000.0) -> dict:
        return {"active": True, "expires_at_epoch": now + 60}

    def test_start_commands_route_when_inactive(self) -> None:
        route = MODULE.route_message("开启快速截屏！", {}, now=1000.0)
        self.assertEqual("start", route["action"])
        self.assertTrue(route["matched"])
        self.assertEqual("start", MODULE.route_message("Please, start fast screenshot mode", {}, now=1000.0)["action"])

    def test_active_mode_accepts_loose_chinese_capture_commands(self) -> None:
        state = self.active_state()
        self.assertEqual("viewport", MODULE.route_message("截图", state, now=1000.0)["mode"])
        self.assertEqual("viewport", MODULE.route_message("帮我截个图", state, now=1000.0)["mode"])
        self.assertEqual("viewport", MODULE.route_message("请截图一下吧", state, now=1000.0)["mode"])
        self.assertEqual("long", MODULE.route_message("来张长截图", state, now=1000.0)["mode"])
        self.assertEqual("full", MODULE.route_message("完整截图", state, now=1000.0)["mode"])

    def test_active_mode_accepts_loose_english_capture_commands(self) -> None:
        state = self.active_state()
        self.assertEqual("viewport", MODULE.route_message("Take a screenshot", state, now=1000.0)["mode"])
        self.assertEqual("viewport", MODULE.route_message("Take a screenshot please", state, now=1000.0)["mode"])
        self.assertEqual("long", MODULE.route_message("Scrolling screenshot", state, now=1000.0)["mode"])
        self.assertEqual("full", MODULE.route_message("Full-page screenshot", state, now=1000.0)["mode"])

    def test_active_mode_blocks_all_other_semantic_work(self) -> None:
        state = self.active_state()
        self.assertEqual("blocked", MODULE.route_message("截图并分析一下", state, now=1000.0)["action"])
        self.assertEqual("blocked", MODULE.route_message("今天天气怎么样", state, now=1000.0)["action"])

    def test_stop_commands_work_only_as_mode_control(self) -> None:
        state = self.active_state()
        self.assertEqual("stop", MODULE.route_message("退出快速截屏", state, now=1000.0)["action"])
        self.assertEqual("stop", MODULE.route_message("Exit fast screenshot mode", state, now=1000.0)["action"])

    def test_inactive_capture_requests_prompt_for_fast_mode(self) -> None:
        state = {"active": True, "expires_at_epoch": 999.0}
        route = MODULE.route_message("截图", state, now=1000.0)
        self.assertTrue(route["matched"])
        self.assertEqual("inactive_capture", route["action"])

    def test_heartbeat_uses_content_free_runner_uptime_probe(self) -> None:
        command = MODULE.heartbeat_command("fixture-session")
        self.assertEqual(["agent-device", "prepare", "ios-runner"], command[:3])
        self.assertNotIn("alert", command)
        self.assertNotIn("screenshot", command)

    def test_wrapper_routes_without_machine_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = os.environ.copy()
            for name in (
                "CSI_AGENT_DEVICE_ENV",
                "XDG_CONFIG_HOME",
                "SCREENSHOT_STITCHER_PYTHON",
            ):
                environment.pop(name, None)
            environment.update(
                {
                    "HOME": str(root),
                    "CSI_FAST_CAPTURE_PYTHON": sys.executable,
                    "CSI_FAST_CAPTURE_STATE": str(root / "state.json"),
                }
            )
            result = subprocess.run(
                ["sh", str(WRAPPER_PATH), "route", "开启快速截屏"],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("start", json.loads(result.stdout)["action"])


class FastCaptureStateTests(unittest.TestCase):
    def test_route_current_marks_expired_state_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(
                json.dumps({"active": True, "expires_at_epoch": 1.0, "keepalive_pid": 123}),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"CSI_FAST_CAPTURE_STATE": str(state_path)}):
                route = MODULE.route_current("截图")
            self.assertTrue(route["matched"])
            self.assertEqual("inactive_capture", route["action"])
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertFalse(payload["active"])
            self.assertIsNone(payload["keepalive_pid"])

    def test_deactivate_does_not_signal_unverified_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "active": True,
                        "expires_at_epoch": MODULE.time.time() + 60,
                        "keepalive_pid": 123,
                        "keepalive_nonce": "fixture",
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(os.environ, {"CSI_FAST_CAPTURE_STATE": str(state_path)}),
                mock.patch.object(MODULE, "process_matches", return_value=False),
                mock.patch.object(MODULE.os, "kill") as kill,
            ):
                payload = MODULE.deactivate()
            self.assertTrue(payload["was_active"])
            kill.assert_not_called()


class WiredConnectionGateTests(unittest.TestCase):
    def completed_inventory(self, command: list[str], entries: list[dict]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps(entries), "")

    def test_gate_accepts_xcode_usb_interface(self) -> None:
        def fake_run(command, label, **kwargs):
            return self.completed_inventory(
                command,
                [
                    {
                        "name": "fixture-phone",
                        "identifier": "fixture-id",
                        "platform": "com.apple.platform.iphoneos",
                        "available": True,
                        "interface": "usb",
                    }
                ],
            )

        with (
            mock.patch.dict(os.environ, {"AGENT_DEVICE_DEVICE": "fixture-phone"}),
            mock.patch.object(MODULE, "run_command", side_effect=fake_run) as run,
        ):
            connection = MODULE.verify_wired_device_connection()

        self.assertEqual({"interface": "usb"}, connection)
        self.assertEqual(
            ["xcrun", "xcdevice", "list", "--timeout", "5"],
            run.call_args.args[0],
        )

    def test_gate_rejects_network_interface(self) -> None:
        def fake_run(command, label, **kwargs):
            return self.completed_inventory(
                command,
                [
                    {
                        "name": "fixture-phone",
                        "identifier": "fixture-id",
                        "platform": "com.apple.platform.iphoneos",
                        "available": True,
                        "interface": "network",
                    }
                ],
            )

        with (
            mock.patch.dict(os.environ, {"AGENT_DEVICE_DEVICE": "fixture-phone"}),
            mock.patch.object(MODULE, "run_command", side_effect=fake_run),
        ):
            with self.assertRaisesRegex(MODULE.FastModeError, "network.*usb"):
                MODULE.verify_wired_device_connection()

    def test_gate_can_match_exact_device_identifier(self) -> None:
        def fake_run(command, label, **kwargs):
            return self.completed_inventory(
                command,
                [
                    {
                        "name": "fixture-phone",
                        "identifier": "fixture-id",
                        "platform": "com.apple.platform.iphoneos",
                        "available": True,
                        "interface": "usb",
                    }
                ],
            )

        with (
            mock.patch.dict(os.environ, {"AGENT_DEVICE_DEVICE": "fixture-id"}),
            mock.patch.object(MODULE, "run_command", side_effect=fake_run),
        ):
            connection = MODULE.verify_wired_device_connection()

        self.assertEqual({"interface": "usb"}, connection)

    def test_gate_fails_closed_when_device_is_missing(self) -> None:
        def fake_run(command, label, **kwargs):
            return self.completed_inventory(command, [])

        with (
            mock.patch.dict(os.environ, {"AGENT_DEVICE_DEVICE": "fixture-phone"}),
            mock.patch.object(MODULE, "run_command", side_effect=fake_run),
        ):
            with self.assertRaisesRegex(MODULE.FastModeError, "not visible"):
                MODULE.verify_wired_device_connection()


class ForegroundSessionBindingTests(unittest.TestCase):
    def completed(self, command: list[str], payload: dict) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    def test_open_command_has_no_app_bundle_name_or_url(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AGENT_DEVICE_RAW_BIN": "/fixture/agent-device", "AGENT_DEVICE_DEVICE": "fixture-phone"},
        ):
            command = MODULE.foreground_session_open_command("fixture-session")
        self.assertEqual("/fixture/agent-device", command[0])
        self.assertEqual("open", command[1])
        self.assertEqual(
            [
                "/fixture/agent-device",
                "open",
                "--platform",
                "ios",
                "--device",
                "fixture-phone",
                "--session",
                "fixture-session",
                "--no-record",
                "--json",
            ],
            command,
        )

    def test_missing_session_is_bound_to_current_foreground(self) -> None:
        commands: list[list[str]] = []
        inventory_count = 0

        def fake_run(command, label, **kwargs):
            nonlocal inventory_count
            commands.append(command)
            if command[1:3] == ["session", "list"]:
                inventory_count += 1
                sessions = [] if inventory_count == 1 else [{"name": "fixture-session", "createdAt": 2000}]
                return self.completed(command, {"success": True, "data": {"sessions": sessions}})
            if command[1] == "appstate":
                return self.completed(command, {"success": True, "data": {"appBundleId": "com.current.app"}})
            return self.completed(command, {"success": True, "data": {}})

        with (
            mock.patch.dict(
                os.environ,
                {"AGENT_DEVICE_RAW_BIN": "/fixture/agent-device", "AGENT_DEVICE_DEVICE": "fixture-phone"},
            ),
            mock.patch.object(MODULE, "run_command", side_effect=fake_run),
        ):
            binding = MODULE.ensure_foreground_session(
                "fixture-session",
                expected_generation="1000",
                force_rebind=False,
            )

        self.assertTrue(binding["session_rebound"])
        self.assertEqual("2000", binding["session_created_at"])
        self.assertTrue(any(command[1] == "open" for command in commands))
        self.assertFalse(any(command[1] == "close" for command in commands))

    def test_stale_session_is_released_then_rebound_without_app_target(self) -> None:
        commands: list[list[str]] = []
        inventory_count = 0

        def fake_run(command, label, **kwargs):
            nonlocal inventory_count
            commands.append(command)
            if command[1:3] == ["session", "list"]:
                inventory_count += 1
                created_at = 1000 if inventory_count == 1 else 2000
                return self.completed(
                    command,
                    {"success": True, "data": {"sessions": [{"name": "fixture-session", "createdAt": created_at}]}},
                )
            if command[1] == "appstate":
                return self.completed(command, {"success": True, "data": {"appBundleId": "com.current.app"}})
            return self.completed(command, {"success": True, "data": {}})

        with (
            mock.patch.dict(
                os.environ,
                {"AGENT_DEVICE_RAW_BIN": "/fixture/agent-device", "AGENT_DEVICE_DEVICE": "fixture-phone"},
            ),
            mock.patch.object(MODULE, "run_command", side_effect=fake_run),
        ):
            binding = MODULE.ensure_foreground_session(
                "fixture-session",
                expected_generation="999",
                force_rebind=False,
            )
            expected_open_command = MODULE.foreground_session_open_command("fixture-session")

        action_order = [command[1] for command in commands]
        self.assertLess(action_order.index("close"), action_order.index("open"))
        open_command = next(command for command in commands if command[1] == "open")
        self.assertEqual(expected_open_command, open_command)
        self.assertEqual("2000", binding["session_created_at"])

    def test_matching_foreground_session_is_reused(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command, label, **kwargs):
            commands.append(command)
            if command[1:3] == ["session", "list"]:
                return self.completed(
                    command,
                    {"success": True, "data": {"sessions": [{"name": "fixture-session", "createdAt": 1000}]}},
                )
            return self.completed(command, {"success": True, "data": {"appBundleId": "com.current.app"}})

        with (
            mock.patch.dict(os.environ, {"AGENT_DEVICE_RAW_BIN": "/fixture/agent-device"}),
            mock.patch.object(MODULE, "run_command", side_effect=fake_run),
        ):
            binding = MODULE.ensure_foreground_session(
                "fixture-session",
                expected_generation="1000",
                force_rebind=False,
            )

        self.assertFalse(binding["session_rebound"])
        self.assertFalse(any(command[1] in {"open", "close"} for command in commands))

    def test_activate_records_verified_foreground_binding_before_mode_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            device_lock = root / "device.lock"
            binding = {"session_created_at": "2000", "session_rebound": True}
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "CSI_FAST_CAPTURE_STATE": str(state_path),
                        "CSI_DEVICE_LOCK": str(device_lock),
                    },
                ),
                mock.patch.object(
                    MODULE,
                    "verify_wired_device_connection",
                    return_value={"interface": "usb"},
                ) as verify_connection,
                mock.patch.object(MODULE, "run_command") as run,
                mock.patch.object(MODULE, "ensure_foreground_session", return_value=binding) as ensure,
                mock.patch.object(MODULE, "ensure_keepalive", side_effect=lambda payload, session: payload),
            ):
                payload = MODULE.activate("fixture-session")

            self.assertTrue(payload["active"])
            self.assertTrue(payload["session_rebound"])
            self.assertEqual("usb", payload["connection_interface"])
            verify_connection.assert_called_once_with()
            ensure.assert_called_once_with(
                "fixture-session",
                expected_generation=None,
                force_rebind=True,
            )
            run.assert_called_once()
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(state["active"])
            self.assertEqual("current_foreground", state["session_binding"])
            self.assertEqual("usb", state["connection_interface_at_activation"])
            self.assertEqual("2000", state["agent_session_created_at"])

    def test_activate_checks_connection_before_runner_warmup_and_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events: list[str] = []

            def fake_connection():
                events.append("usb-connection")
                return {"interface": "usb"}

            def fake_run(command, label, **kwargs):
                events.append("runner-warmup")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_binding(*args, **kwargs):
                events.append("foreground-binding")
                return {"session_created_at": "2000", "session_rebound": True}

            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "CSI_FAST_CAPTURE_STATE": str(root / "state.json"),
                        "CSI_DEVICE_LOCK": str(root / "device.lock"),
                    },
                ),
                mock.patch.object(MODULE, "verify_wired_device_connection", side_effect=fake_connection),
                mock.patch.object(MODULE, "run_command", side_effect=fake_run),
                mock.patch.object(MODULE, "ensure_foreground_session", side_effect=fake_binding),
                mock.patch.object(MODULE, "ensure_keepalive", side_effect=lambda payload, session: payload),
            ):
                MODULE.activate("fixture-session")

            self.assertEqual(
                ["usb-connection", "runner-warmup", "foreground-binding"],
                events,
            )

    def test_activate_stops_before_runner_when_connection_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "CSI_FAST_CAPTURE_STATE": str(root / "state.json"),
                        "CSI_DEVICE_LOCK": str(root / "device.lock"),
                    },
                ),
                mock.patch.object(
                    MODULE,
                    "verify_wired_device_connection",
                    side_effect=MODULE.FastModeError("connect by USB"),
                ),
                mock.patch.object(MODULE, "run_command") as run,
                mock.patch.object(MODULE, "ensure_foreground_session") as ensure,
                mock.patch.object(MODULE, "deactivate") as deactivate,
            ):
                with self.assertRaisesRegex(MODULE.FastModeError, "connect by USB"):
                    MODULE.activate("fixture-session")

            run.assert_not_called()
            ensure.assert_not_called()
            deactivate.assert_called_once_with()

    def test_long_capture_rebinds_foreground_session_before_running_capture_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device_lock = root / "device.lock"
            events: list[str] = []
            mode_state = {
                "active": True,
                "expires_at_epoch": MODULE.time.time() + 60,
                "session": "fixture-session",
                "agent_session_created_at": "1000",
            }

            def fake_ensure(*args, **kwargs):
                events.append("ensure-session")
                return {"session_created_at": "2000", "session_rebound": True}

            def fake_capture(command, **kwargs):
                events.append("capture-pipeline")
                return subprocess.CompletedProcess(command, 0, json.dumps({"exit_code": 0}), "")

            with (
                mock.patch.dict(os.environ, {"CSI_DEVICE_LOCK": str(device_lock)}),
                mock.patch.object(
                    MODULE,
                    "route_current",
                    return_value={"action": "capture", "mode": "long"},
                ),
                mock.patch.object(MODULE, "refresh_and_ensure_keepalive", return_value=mode_state),
                mock.patch.object(MODULE, "ensure_foreground_session", side_effect=fake_ensure) as ensure,
                mock.patch.object(MODULE, "record_session_binding") as record,
                mock.patch.object(MODULE.subprocess, "run", side_effect=fake_capture),
            ):
                payload = MODULE.capture(
                    "长截图",
                    str(root / "long.png"),
                    str(root / "work"),
                    "fixture-session",
                    90.0,
                )

            self.assertEqual(["ensure-session", "capture-pipeline"], events)
            ensure.assert_called_once_with(
                "fixture-session",
                expected_generation="1000",
                force_rebind=True,
            )
            record.assert_called_once_with(
                "fixture-session",
                {"session_created_at": "2000", "session_rebound": True},
            )
            self.assertTrue(payload["fast_capture_mode"])
            self.assertEqual("long", payload["routed_mode"])

    def test_capture_rebind_scope_preserves_viewport_and_refreshes_full(self) -> None:
        cases = (
            ("viewport", "截图", False),
            ("full", "全截图", True),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device_lock = root / "device.lock"
            mode_state = {
                "active": True,
                "expires_at_epoch": MODULE.time.time() + 60,
                "session": "fixture-session",
                "agent_session_created_at": "1000",
            }

            for mode, message, force_rebind in cases:
                with self.subTest(mode=mode):
                    with (
                        mock.patch.dict(os.environ, {"CSI_DEVICE_LOCK": str(device_lock)}),
                        mock.patch.object(
                            MODULE,
                            "route_current",
                            return_value={"action": "capture", "mode": mode},
                        ),
                        mock.patch.object(MODULE, "refresh_and_ensure_keepalive", return_value=mode_state),
                        mock.patch.object(
                            MODULE,
                            "ensure_foreground_session",
                            return_value={"session_created_at": "2000", "session_rebound": force_rebind},
                        ) as ensure,
                        mock.patch.object(MODULE, "record_session_binding"),
                        mock.patch.object(
                            MODULE.subprocess,
                            "run",
                            return_value=subprocess.CompletedProcess(
                                ["capture"],
                                0,
                                json.dumps({"exit_code": 0}),
                                "",
                            ),
                        ),
                    ):
                        MODULE.capture(
                            message,
                            str(root / f"{mode}.png"),
                            None,
                            "fixture-session",
                            90.0,
                        )

                    ensure.assert_called_once_with(
                        "fixture-session",
                        expected_generation="1000",
                        force_rebind=force_rebind,
                    )


if __name__ == "__main__":
    unittest.main()
