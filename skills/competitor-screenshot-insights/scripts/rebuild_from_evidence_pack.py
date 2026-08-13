#!/usr/bin/env python3
"""Rebuild a long screenshot from a saved viewport evidence pack without phone use."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Any


class RecoveryError(RuntimeError):
    pass


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def run(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise RecoveryError(f"{label} failed with exit {result.returncode}: {' '.join(result.stdout.splitlines())[-600:]}")
    return result


def run_qa(command: list[str]) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    return result, payload


def select_causal_retry_evidence(
    evidence: list[dict[str, Any]], low_confidence_pairs: list[Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop the later viewport at each flagged seam while preserving both endpoints."""
    count = len(evidence)
    drop_indexes: set[int] = set()
    for raw_pair in low_confidence_pairs:
        if not isinstance(raw_pair, int) or raw_pair < 1 or raw_pair >= count:
            continue
        candidate = raw_pair
        if candidate == count - 1:
            candidate -= 1
        if 0 < candidate < count - 1:
            drop_indexes.add(candidate)
    retained = [item for index, item in enumerate(evidence) if index not in drop_indexes]
    minimum = max(3, (count * 3 + 4) // 5)
    if not drop_indexes or len(retained) < minimum:
        return evidence, []
    dropped_ids = [str(evidence[index].get("evidence_id", f"viewport-{index + 1:03d}")) for index in sorted(drop_indexes)]
    return retained, dropped_ids


def stitch_and_check(
    script_dir: Path,
    paths: list[Path],
    crops: dict[str, Any],
    output: Path,
    mode: str,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], Path]:
    run(
        [
            str(script_dir / "stitch-long-screenshot.sh"),
            "--top-crop", str(crops["top_crop"]),
            "--bottom-crop", str(crops["bottom_crop"]),
            "--x-margin", str(crops["x_margin"]),
            "-o", str(output),
            *map(str, paths),
        ],
        "offline restitch",
    )
    stitch_report = Path(str(output) + ".stitch.json")
    qa_result, qa_payload = run_qa(
        [
            str(script_dir / "qa-stitched-output.sh"),
            "--mode", mode,
            "--stitched", str(output),
            "--report", str(stitch_report),
        ]
    )
    return qa_result, qa_payload, stitch_report


def recover(pack_path: Path, output: Path, mode: str, overwrite: bool) -> dict[str, Any]:
    if not pack_path.is_file():
        raise RecoveryError(f"Evidence pack does not exist: {pack_path}")
    if not output.is_absolute() or output.suffix.lower() != ".png":
        raise RecoveryError("--output must be an absolute .png path")
    if output.exists() and not overwrite:
        raise RecoveryError(f"Output already exists: {output}")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    evidence = [item for item in pack.get("evidence", []) if item.get("quality", {}).get("hard_pass")]
    evidence.sort(key=lambda item: item["capture_order"])
    paths = [Path(item["path"]).expanduser().resolve() for item in evidence]
    if len(paths) < 2:
        raise RecoveryError("At least two hard-quality ordered viewports are required to restitch")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RecoveryError(f"Evidence pack references missing viewports: {missing}")
    crops = pack.get("crops") or {}
    required_crops = ("top_crop", "bottom_crop", "x_margin")
    if any(not isinstance(crops.get(key), int) or crops[key] < 0 for key in required_crops):
        raise RecoveryError("Evidence pack is missing non-negative integer crop geometry")
    script_dir = Path(__file__).resolve().parent
    output.parent.mkdir(parents=True, exist_ok=True)
    qa_result, qa_payload, qa_report = stitch_and_check(script_dir, paths, crops, output, mode)
    fallback_used = False
    dropped_evidence_ids: list[str] = []
    delivered_evidence = evidence
    if qa_result.returncode != 0:
        delivered_evidence, dropped_evidence_ids = select_causal_retry_evidence(
            evidence, qa_payload.get("low_confidence_pairs") or []
        )
        if not dropped_evidence_ids:
            raise RecoveryError(
                f"offline restitch QA failed with exit {qa_result.returncode}: {' '.join(qa_result.stdout.splitlines())[-600:]}"
            )
        retry_output = output.with_name(f"{output.stem}.retry{output.suffix}")
        retry_paths = [Path(item["path"]).expanduser().resolve() for item in delivered_evidence]
        retry_result, retry_payload, retry_report = stitch_and_check(script_dir, retry_paths, crops, retry_output, mode)
        if retry_result.returncode != 0:
            raise RecoveryError(
                f"offline restitch QA retry failed with exit {retry_result.returncode}: {' '.join(retry_result.stdout.splitlines())[-600:]}"
            )
        os.replace(retry_output, output)
        os.replace(retry_report, qa_report)
        retry_log = Path(str(retry_output) + ".stitch.log")
        if retry_log.is_file():
            os.replace(retry_log, Path(str(output) + ".stitch.log"))
        qa_payload = retry_payload
        fallback_used = True
    report = {
        "schema_version": 1,
        "decision": "accept",
        "source_pack": str(pack_path),
        "output": str(output),
        "qa_report": str(qa_report),
        "source_viewport_count": len(evidence),
        "viewport_count": len(delivered_evidence),
        "fallback_used": fallback_used,
        "fallback": "drop_later_frame_at_low_confidence_seams" if fallback_used else None,
        "dropped_evidence_ids": dropped_evidence_ids,
        "qa_decision": qa_payload.get("decision"),
        "qa_warnings": qa_payload.get("warnings", []),
        "agent_device_commands": 0,
    }
    atomic_write(output.with_suffix(output.suffix + ".recovery.json"), report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("fast", "verified"), default="fast")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report = recover(args.pack.expanduser().resolve(), args.output.expanduser(), args.mode, args.overwrite)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (RecoveryError, json.JSONDecodeError) as error:
        print(json.dumps({"decision": "reject", "reason": str(error)}, ensure_ascii=False, indent=2))
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
