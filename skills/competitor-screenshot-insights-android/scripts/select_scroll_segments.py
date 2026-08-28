#!/usr/bin/env python3
"""Validate extracted scroll frames and exclude diagnostic safety frames."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any


EXIT_PASS = 0
EXIT_FAIL = 10
EXIT_ERROR = 2


class SelectionError(ValueError):
    pass


def emit(payload: dict[str, Any], exit_code: int) -> int:
    print(json.dumps({"exit_code": exit_code, **payload}, ensure_ascii=False, indent=2))
    return exit_code


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SelectionError(f"Unable to read {label} {path}: {error}") from error
    if not isinstance(payload, dict):
        raise SelectionError(f"{label} must contain a JSON object: {path}")
    return payload


def parse_json_output(text: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        start = text.find("{")
        if start < 0:
            raise SelectionError(f"{label} returned no JSON: {text[-1000:]}") from error
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError as nested:
            raise SelectionError(f"{label} returned invalid JSON: {text[-1000:]}") from nested
    if not isinstance(payload, dict):
        raise SelectionError(f"{label} returned a non-object JSON value")
    return payload


def validate_probe(
    script_dir: Path,
    previous: Path,
    probe: Path,
    top_crop: int,
    bottom_crop: int,
    x_margin: int,
) -> tuple[int, dict[str, Any]]:
    command = [
        str(script_dir / "validate-probe.sh"),
        "--mode",
        "fast",
        "--previous",
        str(previous),
        "--probe",
        str(probe),
        "--top-crop",
        str(top_crop),
        "--bottom-crop",
        str(bottom_crop),
        "--x-margin",
        str(x_margin),
    ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return result.returncode, parse_json_output(result.stdout, "validate-probe")


def strong_pair(payload: dict[str, Any], min_confidence: float, min_consensus: float) -> bool:
    pair = payload.get("pair") or {}
    return bool(
        pair.get("mode") == "matched"
        and float(pair.get("confidence", 0.0)) >= min_confidence
        and float(pair.get("consensus", 0.0)) >= min_consensus
        and int(pair.get("offset_px", 0)) > 0
    )


def visual_terminal_is_complete(
    *,
    bottom_confirmed_no_progress: bool,
    sequence_confirmed_no_progress: bool,
    cumulative_progress_px: float,
    coverage_ratio: float,
    minimum_coverage_ratio: float,
) -> bool:
    """Accept a visual bottom without trusting an overestimated semantic height."""
    if not bottom_confirmed_no_progress or cumulative_progress_px <= 0:
        return False
    return bool(
        coverage_ratio >= minimum_coverage_ratio
        or sequence_confirmed_no_progress
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", required=True)
    parser.add_argument("--extraction-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report")
    parser.add_argument("--bottom-screenshot")
    parser.add_argument("--base-gesture-count", type=int, required=True)
    parser.add_argument("--required-progress-px", type=float, required=True)
    parser.add_argument("--visible-height-px", type=float, required=True)
    parser.add_argument("--top-crop", type=int, default=0)
    parser.add_argument("--bottom-crop", type=int, default=0)
    parser.add_argument("--x-margin", type=int, default=0)
    parser.add_argument("--safety-min-confidence", type=float, default=0.50)
    parser.add_argument("--safety-min-consensus", type=float, default=0.20)
    parser.add_argument("--minimum-coverage-ratio", type=float, default=0.80)
    args = parser.parse_args()

    initial = Path(args.initial).expanduser().resolve()
    extraction_path = Path(args.extraction_report).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    bottom_screenshot = (
        Path(args.bottom_screenshot).expanduser().resolve()
        if args.bottom_screenshot
        else None
    )
    values = (
        args.required_progress_px,
        args.visible_height_px,
        args.safety_min_confidence,
        args.safety_min_consensus,
        args.minimum_coverage_ratio,
    )
    if not all(math.isfinite(value) for value in values):
        raise SelectionError("Numeric inputs must be finite")
    if not initial.is_file():
        raise SelectionError(f"Initial screenshot does not exist: {initial}")
    if not extraction_path.is_file():
        raise SelectionError(f"Extraction report does not exist: {extraction_path}")
    if bottom_screenshot and not bottom_screenshot.is_file():
        raise SelectionError(f"Bottom screenshot does not exist: {bottom_screenshot}")
    if args.base_gesture_count < 0:
        raise SelectionError("Base gesture count must be non-negative")
    if args.required_progress_px < 0 or args.visible_height_px <= 0:
        raise SelectionError("Progress must be non-negative and visible height must be positive")
    if not 0 < args.minimum_coverage_ratio <= 1:
        raise SelectionError("Minimum coverage ratio must be in (0, 1]")
    if output_dir.exists() and any(output_dir.glob("segment-*.png")):
        raise SelectionError(f"Output directory already contains segments: {output_dir}")

    extraction = load_json(extraction_path, "extraction report")
    selections = sorted(
        extraction.get("selections", []), key=lambda item: int(item.get("gesture", 0))
    )
    if args.required_progress_px > 0 and not selections:
        raise SelectionError("Extraction report contains no selected frames")

    output_dir.mkdir(parents=True, exist_ok=True)
    initial_destination = output_dir / "segment-000.png"
    shutil.copy2(initial, initial_destination)
    accepted: list[dict[str, Any]] = [
        {
            "segment": str(initial_destination),
            "source": str(initial),
            "role": "initial",
            "progress_px": 0,
        }
    ]
    excluded: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    cumulative_progress = 0.0
    tolerance = max(
        120.0,
        min(args.visible_height_px * 0.12, args.required_progress_px * 0.15),
    )

    def coverage_ratio() -> float:
        if args.required_progress_px <= 0:
            return 1.0
        return cumulative_progress / args.required_progress_px

    def coverage_complete() -> bool:
        return bool(
            args.required_progress_px <= 0
            or (
                cumulative_progress + tolerance >= args.required_progress_px
                and coverage_ratio() >= args.minimum_coverage_ratio
            )
        )

    script_dir = Path(__file__).resolve().parent
    previous = initial_destination
    terminal_no_progress = False
    for selection in selections:
        gesture = int(selection.get("gesture", 0))
        role = selection.get("role") or (
            "base" if gesture <= args.base_gesture_count else "safety"
        )
        source_value = selection.get("path") or selection.get("output")
        if not source_value:
            raise SelectionError(f"Gesture {gesture} has no extracted-frame path")
        source = Path(source_value).expanduser()
        if not source.is_absolute():
            source = extraction_path.parent / source
        source = source.resolve()
        if not source.is_file():
            raise SelectionError(f"Extracted frame does not exist: {source}")
        if terminal_no_progress:
            excluded.append(
                {"gesture": gesture, "role": role, "source": str(source), "reason": "after_terminal_no_progress"}
            )
            continue
        if role == "safety" and coverage_complete():
            excluded.append(
                {
                    "gesture": gesture,
                    "role": role,
                    "source": str(source),
                    "reason": "base_sequence_already_covers_expected_progress",
                }
            )
            continue

        status, validation = validate_probe(
            script_dir,
            previous,
            source,
            args.top_crop,
            args.bottom_crop,
            args.x_margin,
        )
        validations.append(
            {"gesture": gesture, "role": role, "source": str(source), "status": status, "result": validation}
        )
        if status == EXIT_PASS:
            if role == "safety" and not strong_pair(
                validation, args.safety_min_confidence, args.safety_min_consensus
            ):
                excluded.append(
                    {
                        "gesture": gesture,
                        "role": role,
                        "source": str(source),
                        "reason": "safety_frame_requires_strong_matched_overlap",
                    }
                )
                continue
            pair = validation.get("pair") or {}
            offset = float(pair.get("offset_px", 0.0))
            if offset <= 0:
                raise SelectionError(f"Accepted gesture {gesture} has no positive offset")
            destination = output_dir / f"segment-{len(accepted):03d}.png"
            shutil.copy2(source, destination)
            cumulative_progress += offset
            accepted.append(
                {
                    "segment": str(destination),
                    "source": str(source),
                    "gesture": gesture,
                    "role": role,
                    "progress_px": offset,
                    "pair": pair,
                    "decision": validation.get("decision"),
                }
            )
            previous = destination
            continue

        reason = str(validation.get("reason") or "probe_validation_failed")
        if status == EXIT_FAIL and reason in {"duplicate_or_no_progress", "no_vertical_progress"}:
            excluded.append(
                {"gesture": gesture, "role": role, "source": str(source), "reason": reason}
            )
            terminal_no_progress = True
            continue
        if role == "safety":
            excluded.append(
                {"gesture": gesture, "role": role, "source": str(source), "reason": reason}
            )
            continue
        raise SelectionError(f"Base gesture {gesture} failed validation: {reason}")

    bottom_confirmed_no_progress = False
    if not coverage_complete() and bottom_screenshot is not None:
        status, validation = validate_probe(
            script_dir,
            previous,
            bottom_screenshot,
            args.top_crop,
            args.bottom_crop,
            args.x_margin,
        )
        validations.append(
            {"role": "bottom", "source": str(bottom_screenshot), "status": status, "result": validation}
        )
        reason = str(validation.get("reason") or "bottom_validation_failed")
        if status == EXIT_PASS and strong_pair(
            validation, args.safety_min_confidence, args.safety_min_consensus
        ):
            pair = validation.get("pair") or {}
            offset = float(pair.get("offset_px", 0.0))
            destination = output_dir / f"segment-{len(accepted):03d}.png"
            shutil.copy2(bottom_screenshot, destination)
            cumulative_progress += offset
            accepted.append(
                {
                    "segment": str(destination),
                    "source": str(bottom_screenshot),
                    "role": "bottom",
                    "progress_px": offset,
                    "pair": pair,
                    "decision": validation.get("decision"),
                }
            )
            previous = destination
        elif status == EXIT_FAIL and reason in {"duplicate_or_no_progress", "no_vertical_progress"}:
            bottom_confirmed_no_progress = True
            excluded.append(
                {"role": "bottom", "source": str(bottom_screenshot), "reason": reason}
            )
        else:
            excluded.append(
                {"role": "bottom", "source": str(bottom_screenshot), "reason": reason}
            )

    visual_terminal_accepted = visual_terminal_is_complete(
        bottom_confirmed_no_progress=bottom_confirmed_no_progress,
        sequence_confirmed_no_progress=terminal_no_progress,
        cumulative_progress_px=cumulative_progress,
        coverage_ratio=coverage_ratio(),
        minimum_coverage_ratio=args.minimum_coverage_ratio,
    )
    complete = coverage_complete() or visual_terminal_accepted
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else output_dir / "sequence.json"
    )
    report = {
        "check": "scroll_sequence",
        "decision": "accept" if complete else "reject",
        "base_gesture_count": args.base_gesture_count,
        "required_progress_px": round(args.required_progress_px, 3),
        "visible_height_px": round(args.visible_height_px, 3),
        "coverage_tolerance_px": round(tolerance, 3),
        "cumulative_progress_px": round(cumulative_progress, 3),
        "coverage_ratio": round(coverage_ratio(), 6),
        "sequence_confirmed_no_progress": terminal_no_progress,
        "bottom_confirmed_no_progress": bottom_confirmed_no_progress,
        "visual_terminal_accepted": visual_terminal_accepted,
        "accepted": accepted,
        "excluded": excluded,
        "validations": validations,
        "segment_paths": [item["segment"] for item in accepted],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not complete:
        return emit(
            {
                **report,
                "report": str(report_path),
                "reason": "accepted_sequence_does_not_cover_expected_progress",
                "suggested_action": "fall_back_to_targeted_still_capture",
            },
            EXIT_FAIL,
        )
    return emit({**report, "report": str(report_path)}, EXIT_PASS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SelectionError as error:
        raise SystemExit(
            emit(
                {"check": "scroll_sequence", "decision": "error", "reason": str(error)},
                EXIT_ERROR,
            )
        )
