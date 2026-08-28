#!/usr/bin/env python3
"""Select one settled frame after each recorded scroll using media timestamps."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

import cv2
import numpy as np


class ExtractionError(ValueError):
    pass


def load_events(path: Path) -> list[dict[str, float]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExtractionError(f"Unable to read telemetry {path}: {error}") from error
    events: list[dict[str, float]] = []
    for raw in payload.get("events", []):
        if raw.get("kind") not in {"swipe", "pan"}:
            continue
        start = float(raw.get("tMs", math.nan))
        duration = float(raw.get("durationMs", math.nan))
        if not math.isfinite(start) or not math.isfinite(duration) or duration < 0:
            raise ExtractionError("Telemetry contains an invalid gesture timestamp")
        events.append({"start_ms": start, "end_ms": start + duration})
    if not events:
        raise ExtractionError("Telemetry contains no swipe or pan events")
    if any(first["start_ms"] >= second["start_ms"] for first, second in zip(events, events[1:])):
        raise ExtractionError("Telemetry gesture timestamps are not strictly increasing")
    return events


def body_gray(
    frame: np.ndarray, top_crop: int, bottom_crop: int, x_margin: int
) -> tuple[np.ndarray, float, float]:
    height, width = frame.shape[:2]
    if min(top_crop, bottom_crop, x_margin) < 0:
        raise ExtractionError("Crop values must be non-negative")
    if top_crop + bottom_crop >= height or x_margin * 2 >= width:
        raise ExtractionError("Crop values remove the whole video frame")
    bottom = height - bottom_crop if bottom_crop else height
    right = width - x_margin if x_margin else width
    gray = cv2.cvtColor(frame[top_crop:bottom, x_margin:right], cv2.COLOR_BGR2GRAY)
    if gray.shape[1] > 256:
        scale = 256 / gray.shape[1]
        gray = cv2.resize(
            gray,
            (256, max(1, round(gray.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    near_black = float(np.count_nonzero(gray < 8) / gray.size)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return cv2.GaussianBlur(gray, (5, 5), 0), near_black, sharpness


def decode_metrics(
    video: Path, top_crop: int, bottom_crop: int, x_margin: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ExtractionError(f"Unable to open video: {video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    metrics: list[dict[str, Any]] = []
    previous_ms = -1.0
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        timestamp_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC))
        if not math.isfinite(timestamp_ms) or timestamp_ms <= previous_ms:
            if not math.isfinite(fps) or fps <= 0:
                capture.release()
                raise ExtractionError("Video has no usable presentation timestamps")
            timestamp_ms = index * 1000.0 / fps
        gray, near_black, sharpness = body_gray(
            frame, top_crop, bottom_crop, x_margin
        )
        metrics.append(
            {
                "index": index,
                "timestamp_ms": timestamp_ms,
                "gray": gray,
                "near_black_ratio": near_black,
                "sharpness": sharpness,
            }
        )
        previous_ms = timestamp_ms
        index += 1
    capture.release()
    if not metrics:
        raise ExtractionError("Video decoded zero frames")
    return metrics, {
        "width": width,
        "height": height,
        "frame_count": len(metrics),
        "duration_ms": metrics[-1]["timestamp_ms"],
        "metadata_fps": fps,
    }


def frame_difference(first: np.ndarray, second: np.ndarray) -> float:
    return float(cv2.absdiff(first, second).mean() / 255.0)


def choose_interval_frame(
    frames: list[dict[str, Any]], start_ms: float, end_ms: float, near_black_limit: float
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    candidates = [
        frame
        for frame in frames
        if start_ms <= frame["timestamp_ms"] <= end_ms
        and frame["near_black_ratio"] < near_black_limit
    ]
    if not candidates:
        return None, {"reason": "no_non_black_frame_in_settled_interval"}
    midpoint = (start_ms + end_ms) / 2.0
    stabilities: list[float] = []
    for index, candidate in enumerate(candidates):
        differences: list[float] = []
        if index:
            differences.append(
                frame_difference(candidates[index - 1]["gray"], candidate["gray"])
            )
        if index + 1 < len(candidates):
            differences.append(
                frame_difference(candidate["gray"], candidates[index + 1]["gray"])
            )
        stabilities.append(float(np.mean(differences)) if differences else 0.0)
    median = float(np.median(stabilities))
    mad = float(np.median(np.abs(np.asarray(stabilities) - median)))
    stability_limit = median + max(mad, 0.002)
    sharpness_values = np.asarray([item["sharpness"] for item in candidates])
    sharpness_scale = max(float(np.median(sharpness_values)), 1.0)
    stability_scale = max(median, 0.002)
    half_span = max((end_ms - start_ms) / 2.0, 1.0)
    scored: list[tuple[float, dict[str, Any], float]] = []
    for candidate, stability in zip(candidates, stabilities):
        if stability > stability_limit and len(candidates) > 2:
            continue
        midpoint_penalty = abs(candidate["timestamp_ms"] - midpoint) / half_span
        score = (
            candidate["sharpness"] / sharpness_scale
            - 2.0 * stability / stability_scale
            - 0.15 * midpoint_penalty
        )
        scored.append((score, candidate, stability))
    if not scored:
        scored = [
            (-stability, candidate, stability)
            for candidate, stability in zip(candidates, stabilities)
        ]
    score, selected, stability = max(
        scored,
        key=lambda item: (item[0], -abs(item[1]["timestamp_ms"] - midpoint)),
    )
    return selected, {
        "candidate_count": len(candidates),
        "median_neighbor_difference": round(median, 6),
        "stability_limit": round(stability_limit, 6),
        "selected_neighbor_difference": round(stability, 6),
        "selection_score": round(score, 6),
    }


def write_selected_frames(
    video: Path, output_dir: Path, selections: list[dict[str, Any]]
) -> None:
    wanted = {item["frame_index"]: item["output"] for item in selections}
    capture = cv2.VideoCapture(str(video))
    index = 0
    written: set[int] = set()
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index in wanted:
            destination = output_dir / wanted[index]
            if not cv2.imwrite(str(destination), frame):
                capture.release()
                raise ExtractionError(f"Unable to write extracted frame: {destination}")
            written.add(index)
        index += 1
    capture.release()
    missing = set(wanted) - written
    if missing:
        raise ExtractionError(f"Unable to decode selected frame indexes: {sorted(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--telemetry", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report")
    parser.add_argument("--top-crop", type=int, default=0)
    parser.add_argument("--bottom-crop", type=int, default=0)
    parser.add_argument("--x-margin", type=int, default=0)
    parser.add_argument("--near-black-ratio", type=float, default=0.85)
    parser.add_argument("--base-gesture-count", type=int)
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    telemetry = Path(args.telemetry).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not video.is_file():
        raise ExtractionError(f"Video does not exist: {video}")
    if not telemetry.is_file():
        raise ExtractionError(f"Telemetry does not exist: {telemetry}")
    events = load_events(telemetry)
    if args.base_gesture_count is not None and not 0 <= args.base_gesture_count <= len(events):
        raise ExtractionError("Base gesture count must be between zero and the telemetry event count")
    frames, video_info = decode_metrics(
        video, args.top_crop, args.bottom_crop, args.x_margin
    )
    video_end_ms = frames[-1]["timestamp_ms"]
    selections: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for number, event in enumerate(events, start=1):
        next_start = (
            events[number]["start_ms"] if number < len(events) else video_end_ms
        )
        start_ms = event["end_ms"]
        if next_start < start_ms:
            reason = (
                "recording_ended_before_gesture_settled"
                if number == len(events)
                else "gesture_intervals_overlap"
            )
            skipped.append({"gesture": number, "reason": reason})
            continue
        selected, diagnostics = choose_interval_frame(
            frames, start_ms, next_start, args.near_black_ratio
        )
        if selected is None:
            skipped.append({"gesture": number, **diagnostics})
            continue
        filename = f"probe-{number:03d}.png"
        selections.append(
            {
                "gesture": number,
                "role": (
                    "base"
                    if args.base_gesture_count is None or number <= args.base_gesture_count
                    else "safety"
                ),
                "frame_index": selected["index"],
                "timestamp_ms": round(selected["timestamp_ms"], 3),
                "interval_ms": [round(start_ms, 3), round(next_start, 3)],
                "near_black_ratio": round(selected["near_black_ratio"], 6),
                "sharpness": round(selected["sharpness"], 3),
                "output": filename,
                **diagnostics,
            }
        )
    if not selections:
        raise ExtractionError("No usable settled frames were found after the gestures")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_selected_frames(video, output_dir, selections)
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else output_dir / "extraction.json"
    )
    report = {
        "video": str(video),
        "telemetry": str(telemetry),
        "video_info": video_info,
        "crops": {
            "top_crop": args.top_crop,
            "bottom_crop": args.bottom_crop,
            "x_margin": args.x_margin,
        },
        "gesture_count": len(events),
        "base_gesture_count": args.base_gesture_count,
        "safety_gesture_count": (
            0 if args.base_gesture_count is None else len(events) - args.base_gesture_count
        ),
        "selected_count": len(selections),
        "selections": selections,
        "skipped": skipped,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report, "report": str(report_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExtractionError as error:
        print(
            json.dumps(
                {"exit_code": 2, "decision": "error", "reason": str(error)},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(2)
