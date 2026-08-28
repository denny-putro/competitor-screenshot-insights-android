#!/usr/bin/env python3
"""Manage the modal, warm fast-capture session."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time
import unicodedata
from typing import Any, Iterator


EXIT_PASS = 0
EXIT_NO_MATCH = 10
EXIT_ERROR = 2
IDLE_TTL_SECONDS = 10 * 60
HEARTBEAT_INTERVAL_SECONDS = 20

START_COMMANDS = {
    "开启快速截屏",
    "开启快速截图",
    "进入快速截屏模式",
    "进入快速截图模式",
    "start fast screenshot mode",
    "enable fast screenshot mode",
    "enter fast screenshot mode",
}

STOP_COMMANDS = {
    "退出快速截屏",
    "退出快速截图",
    "关闭快速截屏",
    "关闭快速截图",
    "退出快速截屏模式",
    "退出快速截图模式",
    "关闭快速截屏模式",
    "关闭快速截图模式",
    "exit fast screenshot mode",
    "stop fast screenshot mode",
    "disable fast screenshot mode",
}

CAPTURE_COMMANDS = {
    "viewport": {
        "截屏",
        "截图",
        "截个屏",
        "截个图",
        "截一张屏",
        "截一张图",
        "来张截屏",
        "来张截图",
        "screenshot",
        "take a screenshot",
        "capture the screen",
        "screen capture",
    },
    "long": {
        "长截屏",
        "长截图",
        "截长屏",
        "截长图",
        "来张长截屏",
        "来张长截图",
        "long screenshot",
        "scrolling screenshot",
        "scroll screenshot",
        "take a long screenshot",
    },
    "full": {
        "全截屏",
        "全截图",
        "完整截屏",
        "完整截图",
        "截全屏",
        "来张全截屏",
        "来张全截图",
        "full screenshot",
        "full-page screenshot",
        "full page screenshot",
        "entire page screenshot",
        "take a full screenshot",
    },
}


class FastModeError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def state_path() -> Path:
    override = os.environ.get("CSI_FAST_CAPTURE_STATE")
    if override:
        return Path(override).expanduser().resolve()
    state_root = os.environ.get("XDG_STATE_HOME")
    base = Path(state_root).expanduser() if state_root else Path.home() / ".local" / "state"
    return (base / "codex" / "competitor-screenshot-insights-android" / "fast-capture-mode.json").resolve()


def state_lock_path() -> Path:
    path = state_path()
    return path.with_suffix(path.suffix + ".lock")


def device_lock_path() -> Path:
    override = os.environ.get("CSI_DEVICE_LOCK")
    if override:
        return Path(override).expanduser().resolve()
    return state_path().with_name("agent-device-workflow.lock")


@contextmanager
def file_lock(path: Path, *, blocking: bool = True) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        operation = fcntl.LOCK_EX
        if not blocking:
            operation |= fcntl.LOCK_NB
        fcntl.flock(handle.fileno(), operation)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_state_unlocked() -> dict[str, Any]:
    try:
        payload = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_state_unlocked(payload: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def normalized_message(message: str) -> str:
    value = unicodedata.normalize("NFKC", message).strip()
    value = re.sub(r"[\s。！？.!?]+$", "", value).strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"^请(?:你)?\s*", "", value)
    value = re.sub(r"^(?:麻烦|帮我|给我)\s*", "", value)
    value = re.sub(r"^please(?:\s+|[,，]\s*)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:could you|can you)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*(?:(?:吧|一下|可以吗|好吗|谢谢)\s*)+$", "", value)
    value = re.sub(r"\s+please$", "", value, flags=re.IGNORECASE)
    return value.strip().lower()


def state_is_active(payload: dict[str, Any], now: float | None = None) -> bool:
    current = time.time() if now is None else now
    expires_at = payload.get("expires_at_epoch")
    return (
        payload.get("active") is True
        and isinstance(expires_at, (int, float))
        and float(expires_at) > current
    )


def capture_mode_for(normalized: str) -> str | None:
    for mode in ("full", "long", "viewport"):
        if normalized in CAPTURE_COMMANDS[mode]:
            return mode
    return None


def route_message(message: str, payload: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    normalized = normalized_message(message)
    active = state_is_active(payload, now=now)
    if normalized in START_COMMANDS:
        return {"matched": True, "action": "start", "mode": None, "active": active, "normalized_prompt": normalized}
    if normalized in STOP_COMMANDS:
        return {"matched": True, "action": "stop", "mode": None, "active": active, "normalized_prompt": normalized}
    mode = capture_mode_for(normalized)
    if not active:
        if mode is not None:
            return {"matched": True, "action": "inactive_capture", "mode": mode, "active": False, "normalized_prompt": normalized}
        return {"matched": False, "action": "none", "mode": None, "active": False, "normalized_prompt": normalized}
    if mode is not None:
        return {"matched": True, "action": "capture", "mode": mode, "active": True, "normalized_prompt": normalized}
    return {"matched": True, "action": "blocked", "mode": None, "active": True, "normalized_prompt": normalized}


def route_current(message: str) -> dict[str, Any]:
    with file_lock(state_lock_path()):
        payload = read_state_unlocked()
        if payload.get("active") is True and not state_is_active(payload):
            payload["active"] = False
            payload["expired_at"] = utc_now()
            payload["keepalive_pid"] = None
            write_state_unlocked(payload)
        return route_message(message, payload)



def agent_device_env(*, select_device: bool = False) -> dict[str, str]:
    """Environment for an Agent Device invocation.

    `AGENT_DEVICE_DEVICE` is recorded by setup for this Skill's own wired-device
    gate, but the CLI also reads it as an implicit `--device` selector. Once a
    session is bound to a device, any command still carrying that selector fails
    with INVALID_ARGS ("already bound to session ... but this request selected
    --device=..."). Device selection belongs to the session-creating `open`,
    which passes `--device` explicitly, so every other call runs without it.
    """
    env = os.environ.copy()
    if not select_device:
        env.pop("AGENT_DEVICE_DEVICE", None)
    return env

def run_command(
    command: list[str],
    label: str,
    timeout: float = 45.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=env if env is not None else agent_device_env(),
        )
    except subprocess.TimeoutExpired as error:
        raise FastModeError(f"{label} timed out") from error
    if result.returncode != 0:
        detail = (result.stdout or result.stderr).strip().replace("\n", " ")[-800:]
        raise FastModeError(f"{label} failed: {detail or f'exit {result.returncode}'}")
    return result


def parse_command_json(result: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    output = (result.stdout or result.stderr).strip()
    start = output.find("{")
    if start < 0:
        raise FastModeError(f"{label} returned no JSON")
    try:
        payload = json.loads(output[start:])
    except json.JSONDecodeError as error:
        raise FastModeError(f"{label} returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise FastModeError(f"{label} returned a non-object JSON value")
    return payload


def adb_binary() -> str:
    return os.environ.get("CSI_ADB_BIN", "").strip() or "adb"


def normalize_device_name(value: str) -> str:
    # adb reports model/device tokens with underscores for spaces.
    return value.replace("_", " ").strip().casefold()


def parse_adb_devices(output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("List of devices"):
            continue
        if stripped.startswith("*"):  # daemon startup chatter
            continue
        fields = stripped.split()
        if len(fields) < 2:
            continue
        entry = {"serial": fields[0], "state": fields[1]}
        for token in fields[2:]:
            key, separator, value = token.partition(":")
            if separator:
                entry[key] = value
        entries.append(entry)
    return entries


def verify_wired_device_connection() -> dict[str, str]:
    device = os.environ.get("AGENT_DEVICE_DEVICE", "").strip()
    serial = os.environ.get("AGENT_DEVICE_SERIAL", "").strip()
    if not device and not serial:
        raise FastModeError(
            "wired Android connection check requires AGENT_DEVICE_DEVICE or AGENT_DEVICE_SERIAL; "
            "connect the device by USB and configure its identifier"
        )
    result = run_command(
        [adb_binary(), "devices", "-l"],
        "wired Android connection check",
        timeout=20.0,
    )
    entries = parse_adb_devices(result.stdout or result.stderr or "")

    # Surface the two states a user must physically resolve before anything else.
    def matches(entry: dict[str, str]) -> bool:
        if serial:
            return entry.get("serial") == serial
        if entry.get("serial") == device:
            return True
        wanted = normalize_device_name(device)
        return any(
            normalize_device_name(entry.get(key, "")) == wanted
            for key in ("model", "device", "product")
        )

    named = [entry for entry in entries if matches(entry)]
    unauthorized = [entry for entry in named if entry.get("state") == "unauthorized"]
    if unauthorized:
        raise FastModeError(
            "Android device is connected but unauthorized; accept the USB debugging "
            "prompt on the device screen, then retry"
        )
    offline = [entry for entry in named if entry.get("state") == "offline"]
    if offline and not [entry for entry in named if entry.get("state") == "device"]:
        raise FastModeError(
            "Android device is reporting 'offline'; reconnect the cable, unlock the device, and retry"
        )

    ready = [entry for entry in named if entry.get("state") == "device"]
    if len(ready) > 1:
        raise FastModeError(
            "wired Android connection check found multiple matching devices; "
            "configure AGENT_DEVICE_SERIAL with the exact adb serial"
        )
    if not ready:
        raise FastModeError(
            "configured Android device is not visible to adb; "
            "connect it by USB, unlock it, enable USB debugging, and retry"
        )

    selected = ready[0]
    # adb reports a `usb:` token only for cable-attached transports; adb-over-network
    # serials arrive as host:port instead. Fast mode is wired-only by design.
    if "usb" not in selected:
        raise FastModeError(
            "adb does not report a USB transport for the configured device "
            f"(serial {selected.get('serial', 'unknown')!r}); "
            "connect it by cable before enabling fast capture mode"
        )
    return {"interface": "usb", "serial": selected.get("serial", "")}


def agent_device_binary() -> str:
    return os.environ.get("AGENT_DEVICE_RAW_BIN", "agent-device")


def agent_device_command(*parts: str) -> list[str]:
    return [agent_device_binary(), *parts]


def session_entry(session: str) -> dict[str, Any] | None:
    result = run_command(
        agent_device_command("session", "list", "--json"),
        "Agent Device session inventory",
        timeout=15.0,
    )
    payload = parse_command_json(result, "Agent Device session inventory")
    data = payload.get("data") or {}
    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        raise FastModeError("Agent Device session inventory returned no session list")
    for entry in sessions:
        if isinstance(entry, dict) and entry.get("name") == session:
            return entry
    return None


def session_generation(entry: dict[str, Any] | None) -> str | None:
    if entry is None:
        return None
    created_at = entry.get("createdAt")
    return None if created_at is None else str(created_at)


def foreground_session_open_command(session: str) -> list[str]:
    command = agent_device_command("open", "--platform", "android")
    device = os.environ.get("AGENT_DEVICE_DEVICE", "").strip()
    if device:
        command.extend(["--device", device])
    command.extend(["--session", session, "--no-record", "--json"])
    return command


def ensure_foreground_session(
    session: str,
    *,
    expected_generation: str | None,
    force_rebind: bool,
) -> dict[str, Any]:
    entry = session_entry(session)
    generation = session_generation(entry)
    should_rebind = force_rebind or entry is None or expected_generation is None or generation != expected_generation
    if should_rebind:
        if entry is not None:
            run_command(
                agent_device_command("close", "--session", session, "--json"),
                "release stale Agent Device session",
                timeout=30.0,
            )
        run_command(
            foreground_session_open_command(session),
            "bind current foreground session",
            timeout=100.0,
        )
        entry = session_entry(session)
        generation = session_generation(entry)
        if entry is None or generation is None:
            raise FastModeError("current foreground session was not created")

    result = run_command(
        agent_device_command("appstate", "--session", session, "--json"),
        "verify current foreground session",
        timeout=30.0,
    )
    payload = parse_command_json(result, "verify current foreground session")
    data = payload.get("data") or {}
    # Android `appstate --json` reports the foreground app as `package`; Apple
    # platforms report `appBundleId`. Accept either so the identity check keeps
    # comparing a real observed value instead of failing on a key name.
    bundle = (
        data.get("package")
        or data.get("appPackage")
        or data.get("appBundleId")
        or data.get("appName")
    )
    if not isinstance(bundle, str) or not bundle.strip():
        raise FastModeError("current foreground session returned no app identity")
    return {
        "session_created_at": generation,
        "session_rebound": should_rebind,
    }


def heartbeat_command(session: str) -> list[str]:
    del session  # Device-scoped probe; the foreground app session is untouched.
    # Android needs no XCTest runner, so there is nothing to build or sign and no
    # `prepare` equivalent. A device enumeration is the content-free keepalive:
    # it names no app, opens nothing, and cannot switch or relaunch the
    # foreground app.
    return [
        "agent-device",
        "devices",
        "--platform",
        "android",
        "--json",
    ]


def process_matches(pid: int, nonce: str) -> bool:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        text=True,
        capture_output=True,
        check=False,
    )
    command = result.stdout.strip()
    return result.returncode == 0 and "fast_capture_mode.py" in command and "_keepalive" in command and nonce in command


def spawn_keepalive(nonce: str, session: str) -> int:
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_keepalive", "--nonce", nonce, "--session", session],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return process.pid


def ensure_keepalive(payload: dict[str, Any], session: str) -> dict[str, Any]:
    pid = payload.get("keepalive_pid")
    nonce = payload.get("keepalive_nonce")
    if isinstance(pid, int) and isinstance(nonce, str) and process_matches(pid, nonce):
        return payload
    nonce = secrets.token_hex(16)
    payload["keepalive_nonce"] = nonce
    payload["keepalive_pid"] = spawn_keepalive(nonce, session)
    return payload


def activate(session: str) -> dict[str, Any]:
    now = time.time()
    with file_lock(state_lock_path()):
        previous = read_state_unlocked()
        already_active = state_is_active(previous, now=now)
    try:
        with file_lock(device_lock_path()):
            connection = verify_wired_device_connection()
            run_command(heartbeat_command(session), "device transport warm-up", timeout=100.0)
            binding = ensure_foreground_session(
                session,
                expected_generation=(
                    str(previous["agent_session_created_at"])
                    if already_active and previous.get("agent_session_created_at") is not None
                    else None
                ),
                force_rebind=not already_active,
            )
    except FastModeError:
        deactivate()
        raise
    now = time.time()
    with file_lock(state_lock_path()):
        payload = {
            "schema_version": 1,
            "active": True,
            "activated_at": previous.get("activated_at") if already_active else utc_now(),
            "activated_at_epoch": previous.get("activated_at_epoch") if already_active else now,
            "last_activity_at": utc_now(),
            "last_activity_epoch": now,
            "expires_at_epoch": now + IDLE_TTL_SECONDS,
            "keepalive_pid": previous.get("keepalive_pid"),
            "keepalive_nonce": previous.get("keepalive_nonce"),
            "session": session,
            "session_binding": "current_foreground",
            "connection_interface_at_activation": connection["interface"],
            "agent_session_created_at": binding["session_created_at"],
            "last_session_rebind_at": (
                utc_now() if binding["session_rebound"] else previous.get("last_session_rebind_at")
            ),
        }
        payload = ensure_keepalive(payload, session)
        write_state_unlocked(payload)
    return {
        "status": "already_active" if already_active else "active",
        "active": True,
        "idle_timeout_seconds": IDLE_TTL_SECONDS,
        "accepted_modes": ["viewport", "long", "full"],
        "connection_interface": connection["interface"],
        "session_rebound": binding["session_rebound"],
    }


def deactivate() -> dict[str, Any]:
    pid: int | None = None
    nonce: str | None = None
    with file_lock(state_lock_path()):
        payload = read_state_unlocked()
        was_active = state_is_active(payload)
        if isinstance(payload.get("keepalive_pid"), int):
            pid = payload["keepalive_pid"]
        if isinstance(payload.get("keepalive_nonce"), str):
            nonce = payload["keepalive_nonce"]
        payload["active"] = False
        payload["deactivated_at"] = utc_now()
        payload["keepalive_pid"] = None
        write_state_unlocked(payload)
    if pid is not None and nonce is not None and process_matches(pid, nonce):
        os.kill(pid, signal.SIGTERM)
    return {"status": "inactive", "active": False, "was_active": was_active}


def refresh_and_ensure_keepalive(session: str) -> dict[str, Any]:
    now = time.time()
    with file_lock(state_lock_path()):
        payload = read_state_unlocked()
        if not state_is_active(payload, now=now):
            raise FastModeError("fast capture mode is not active")
        payload["last_activity_at"] = utc_now()
        payload["last_activity_epoch"] = now
        payload["expires_at_epoch"] = now + IDLE_TTL_SECONDS
        payload = ensure_keepalive(payload, session)
        write_state_unlocked(payload)
        return payload


def record_session_binding(session: str, binding: dict[str, Any]) -> None:
    with file_lock(state_lock_path()):
        payload = read_state_unlocked()
        if not state_is_active(payload) or payload.get("session") != session:
            raise FastModeError("fast capture mode changed while refreshing the foreground session")
        payload["session_binding"] = "current_foreground"
        payload["agent_session_created_at"] = binding["session_created_at"]
        if binding["session_rebound"]:
            payload["last_session_rebind_at"] = utc_now()
        write_state_unlocked(payload)


def capture(message: str, output: str, work_dir: str | None, session: str, max_runtime_seconds: float) -> dict[str, Any]:
    route = route_current(message)
    if route.get("action") != "capture":
        raise FastModeError(f"message is not an accepted active-mode capture command: {route.get('action')}")
    mode_state = refresh_and_ensure_keepalive(session)
    command = [
        sys.executable,
        str(Path(__file__).with_name("capture_current.py")),
        "--mode",
        str(route["mode"]),
        "--output",
        output,
        "--session",
        session,
        "--max-runtime-seconds",
        str(max_runtime_seconds),
    ]
    if work_dir:
        command.extend(["--work-dir", work_dir])
    try:
        with file_lock(device_lock_path()):
            binding = ensure_foreground_session(
                session,
                expected_generation=(
                    str(mode_state["agent_session_created_at"])
                    if mode_state.get("agent_session_created_at") is not None
                    else None
                ),
                force_rebind=route["mode"] in {"long", "full"},
            )
            record_session_binding(session, binding)
            env = agent_device_env()
            env["CSI_DEVICE_LOCK_HELD"] = "1"
            result = subprocess.run(command, text=True, capture_output=True, check=False, env=env)
    except FastModeError:
        deactivate()
        raise
    output_text = result.stdout.strip()
    try:
        payload = json.loads(output_text[output_text.find("{"):])
    except (json.JSONDecodeError, ValueError):
        payload = {"status": "failed", "reason": output_text or result.stderr.strip()}
    payload["fast_capture_mode"] = True
    payload["routed_mode"] = route["mode"]
    if result.returncode != 0:
        raise FastModeError(str(payload.get("reason") or f"capture failed with exit {result.returncode}"))
    return payload


def keepalive(nonce: str, session: str) -> int:
    while True:
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)
        with file_lock(state_lock_path()):
            payload = read_state_unlocked()
            if not state_is_active(payload) or payload.get("keepalive_nonce") != nonce:
                return EXIT_PASS
        try:
            with file_lock(device_lock_path(), blocking=False):
                result = subprocess.run(
                    heartbeat_command(session),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=100.0,
                )
                heartbeat_ok = result.returncode == 0
        except (BlockingIOError, subprocess.TimeoutExpired):
            heartbeat_ok = False
        with file_lock(state_lock_path()):
            payload = read_state_unlocked()
            if payload.get("keepalive_nonce") == nonce:
                payload["last_heartbeat_at"] = utc_now()
                payload["last_heartbeat_ok"] = heartbeat_ok
                write_state_unlocked(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    route_parser = subparsers.add_parser("route")
    route_parser.add_argument("message")
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--session", default=os.environ.get("AGENT_DEVICE_SESSION", "phone-main"))
    subparsers.add_parser("stop")
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--message", required=True)
    capture_parser.add_argument("--output", required=True)
    capture_parser.add_argument("--work-dir")
    capture_parser.add_argument("--session", default=os.environ.get("AGENT_DEVICE_SESSION", "phone-main"))
    capture_parser.add_argument("--max-runtime-seconds", type=float, default=90.0)
    keepalive_parser = subparsers.add_parser("_keepalive")
    keepalive_parser.add_argument("--nonce", required=True)
    keepalive_parser.add_argument("--session", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "route":
            payload = route_current(args.message)
            print(json.dumps(payload, ensure_ascii=False))
            return EXIT_PASS if payload["matched"] else EXIT_NO_MATCH
        if args.command == "start":
            payload = activate(args.session)
        elif args.command == "stop":
            payload = deactivate()
        elif args.command == "capture":
            payload = capture(args.message, args.output, args.work_dir, args.session, args.max_runtime_seconds)
        else:
            return keepalive(args.nonce, args.session)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_PASS
    except FastModeError as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, ensure_ascii=False, indent=2))
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
