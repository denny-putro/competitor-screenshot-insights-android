#!/usr/bin/env python3
"""Execute one fast-mode current-screen capture with bounded recovery."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Iterator


EXIT_PASS = 0
EXIT_FAIL = 10
EXIT_ERROR = 2
READY_TTL_SECONDS = 12 * 60 * 60


class CaptureError(RuntimeError):
    def __init__(self, message: str, exit_code: int = EXIT_FAIL) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_json_output(text: str, label: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise CaptureError(f"{label} returned no JSON", EXIT_ERROR)
    try:
        payload = json.loads(text[start:])
    except json.JSONDecodeError as error:
        raise CaptureError(f"{label} returned invalid JSON", EXIT_ERROR) from error
    if not isinstance(payload, dict):
        raise CaptureError(f"{label} returned a non-object JSON value", EXIT_ERROR)
    return payload



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
    *,
    allowed: tuple[int, ...] = (0,),
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=agent_device_env(),
        )
    except subprocess.TimeoutExpired as error:
        raise CaptureError(f"{label} timed out") from error
    if result.returncode not in allowed:
        detail = (result.stdout or result.stderr).strip().replace("\n", " ")[-800:]
        raise CaptureError(f"{label} failed: {detail or f'exit {result.returncode}'}")
    return result


def state_path() -> Path:
    override = os.environ.get("CSI_CAPTURE_READY_STATE")
    if override:
        return Path(override).expanduser().resolve()
    state_root = os.environ.get("XDG_STATE_HOME")
    base = Path(state_root).expanduser() if state_root else Path.home() / ".local" / "state"
    return (base / "codex" / "competitor-screenshot-insights-android" / "capture-ready.json").resolve()


def device_lock_path() -> Path:
    override = os.environ.get("CSI_DEVICE_LOCK")
    if override:
        return Path(override).expanduser().resolve()
    return state_path().with_name("agent-device-workflow.lock")


@contextmanager
def device_workflow_lock() -> Iterator[None]:
    if os.environ.get("CSI_DEVICE_LOCK_HELD") == "1":
        yield
        return
    path = device_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def readiness_key(session: str) -> str:
    device = os.environ.get("AGENT_DEVICE_DEVICE", "")
    raw = f"{session}\0{device}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def readiness_is_fresh(path: Path, session: str, now: float | None = None) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    checked_at = payload.get("checked_at_epoch")
    if payload.get("readiness_key") != readiness_key(session):
        return False
    if not isinstance(checked_at, (int, float)):
        return False
    current = time.time() if now is None else now
    return 0 <= current - float(checked_at) <= READY_TTL_SECONDS


def record_readiness(path: Path, session: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "readiness_key": readiness_key(session),
                "checked_at": utc_now(),
                "checked_at_epoch": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def ensure_live_readiness(session: str, force: bool = False) -> bool:
    marker = state_path()
    if not force and readiness_is_fresh(marker, session):
        return True
    run_command(["agent-device", "doctor"], "device health check", timeout=30.0)
    record_readiness(marker, session)
    return False


def agent_command(session: str, *parts: str) -> list[str]:
    return ["agent-device", *parts, "--session", session, "--json"]


def run_with_warm_recovery(
    command: list[str],
    label: str,
    *,
    session: str,
    used_cached_readiness: bool,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    try:
        return run_command(command, label, timeout=timeout)
    except CaptureError:
        if not used_cached_readiness:
            raise
        marker = state_path()
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
        ensure_live_readiness(session, force=True)
        return run_command(command, f"{label} retry", timeout=timeout)


def foreground_bundle(session: str) -> str:
    result = run_command(agent_command(session, "appstate"), "foreground app check")
    payload = parse_json_output(result.stdout, "foreground app check")
    data = payload.get("data") or {}
    # Android reports the foreground app as `package`; Apple platforms report
    # `appBundleId`. Accept either so identity checks compare a real value.
    bundle = (
        data.get("package")
        or data.get("appPackage")
        or data.get("appBundleId")
        or data.get("appName")
    )
    if not isinstance(bundle, str) or not bundle.strip():
        raise CaptureError("foreground app check returned no bundle", EXIT_ERROR)
    return bundle.strip()


def validate_output_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute() or path.suffix.lower() != ".png":
        raise CaptureError("--output must be an absolute .png path", EXIT_ERROR)
    path = path.resolve()
    if path.exists():
        raise CaptureError(f"Output already exists: {path}", EXIT_ERROR)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def capture_viewport(
    script_dir: Path,
    output: Path,
    session: str,
    used_cached_readiness: bool,
) -> dict[str, Any]:
    run_with_warm_recovery(
        agent_command(session, "screenshot", str(output)),
        "current viewport screenshot",
        session=session,
        used_cached_readiness=used_cached_readiness,
    )
    check = run_command(
        ["sh", str(script_dir / "check-viewport.sh"), "--image", str(output)],
        "viewport integrity check",
    )
    payload = parse_json_output(check.stdout, "viewport integrity check")
    return {
        "exit_code": EXIT_PASS,
        "mode": "viewport",
        "output": str(output),
        "decision": payload.get("decision"),
        "dimensions": payload.get("dimensions"),
        "used_cached_readiness": used_cached_readiness,
    }


def capture_long(
    script_dir: Path,
    output: Path,
    session: str,
    mode: str,
    used_cached_readiness: bool,
    max_runtime_seconds: float,
    work_dir: Path | None,
) -> dict[str, Any]:
    if mode == "full":
        run_with_warm_recovery(
            agent_command(session, "scroll", "top"),
            "scroll current page to top",
            session=session,
            used_cached_readiness=used_cached_readiness,
        )
    expected_bundle = foreground_bundle(session)
    before = output.with_name(f"{output.stem}.before.png")
    if before.exists():
        raise CaptureError(f"Initial screenshot already exists: {before}", EXIT_ERROR)
    run_with_warm_recovery(
        agent_command(session, "screenshot", str(before)),
        "initial long-screenshot viewport",
        session=session,
        used_cached_readiness=used_cached_readiness,
    )
    run_command(
        ["sh", str(script_dir / "check-viewport.sh"), "--image", str(before)],
        "initial viewport integrity check",
    )
    resolved_work_dir = (
        work_dir.resolve()
        if work_dir is not None
        else output.parent / f"{output.stem}.command-run"
    )
    command = [
        "sh",
        str(script_dir / "capture-long-fast.sh"),
        "--expected-bundle",
        expected_bundle,
        "--before-screenshot",
        str(before),
        "--output",
        str(output),
        "--work-dir",
        str(resolved_work_dir),
        "--capture-extent",
        "auto" if mode == "long" else "full",
        "--max-runtime-seconds",
        str(max_runtime_seconds),
        "--session",
        session,
    ]
    if mode == "long":
        command.append("--allow-current-position")
    result = run_command(
        command,
        f"{mode} screenshot pipeline",
        allowed=(0, EXIT_FAIL),
        timeout=max_runtime_seconds + 15.0,
    )
    payload = parse_json_output(result.stdout, f"{mode} screenshot pipeline")
    if result.returncode != EXIT_PASS:
        evidence_pack = payload.get("viewport_evidence_pack")
        raise CaptureError(
            f"{mode} screenshot failed; evidence pack: {evidence_pack or 'unavailable'}"
        )
    return {
        "exit_code": EXIT_PASS,
        "mode": mode,
        "output": str(output),
        "decision": payload.get("decision"),
        "captured_viewports": payload.get("captured_viewports"),
        "page_complete": payload.get("page_complete"),
        "stop_reason": payload.get("stop_reason"),
        "run_path": str(resolved_work_dir / "run.json"),
        "used_cached_readiness": used_cached_readiness,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("viewport", "long", "full"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--session", default=os.environ.get("AGENT_DEVICE_SESSION", "phone-main"))
    parser.add_argument("--max-runtime-seconds", type=float, default=90.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.max_runtime_seconds <= 0:
            raise CaptureError("--max-runtime-seconds must be positive", EXIT_ERROR)
        if shutil.which("agent-device") is None:
            raise CaptureError("agent-device is unavailable on PATH", EXIT_ERROR)
        output = validate_output_path(args.output)
        script_dir = Path(__file__).resolve().parent
        with device_workflow_lock():
            used_cached_readiness = ensure_live_readiness(args.session)
            if args.mode == "viewport":
                payload = capture_viewport(
                    script_dir,
                    output,
                    args.session,
                    used_cached_readiness,
                )
            else:
                payload = capture_long(
                    script_dir,
                    output,
                    args.session,
                    args.mode,
                    used_cached_readiness,
                    args.max_runtime_seconds,
                    args.work_dir,
                )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_PASS
    except CaptureError as error:
        print(
            json.dumps(
                {
                    "exit_code": error.exit_code,
                    "status": "failed",
                    "reason": " ".join(str(error).splitlines())[:1000],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
