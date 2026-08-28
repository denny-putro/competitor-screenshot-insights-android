#!/usr/bin/env python3
"""Deterministic checks for physical-Android screenshot workflows."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import cv2
import numpy as np


EXIT_PASS = 0
EXIT_FAIL = 10
EXIT_REVIEW = 11
EXIT_ERROR = 2

PAIR_PATTERN = re.compile(
    r"Pair (?P<pair>\d+): confidence=(?P<confidence>[0-9.]+), "
    r"consensus=(?P<consensus>[0-9.]+), offset=(?P<offset>\d+)px, "
    r"overlap=(?P<overlap>\d+)px, mode=(?P<mode>[^,]+), "
    r"(?P<status>.*)"
)


class CheckError(ValueError):
    pass


def emit(payload: dict[str, Any], exit_code: int) -> int:
    payload = {"exit_code": exit_code, **payload}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def plan_scroll_count(args: argparse.Namespace) -> int:
    values = {
        "content_height": args.content_height,
        "visible_height": args.visible_height,
        "scroll_distance": args.scroll_distance,
    }
    if not all(math.isfinite(value) for value in values.values()):
        raise CheckError("Scroll-plan dimensions must be finite numbers")
    if args.content_height <= 0 or args.visible_height <= 0:
        raise CheckError("Content and visible heights must be positive")
    if args.scroll_distance <= 0:
        raise CheckError("Scroll distance must be positive")
    if args.safety_gestures < 0:
        raise CheckError("Safety gestures must be non-negative")
    remaining = max(0.0, args.content_height - args.visible_height)
    base_count = math.ceil(remaining / args.scroll_distance)
    count = base_count + args.safety_gestures if base_count else 0
    return emit(
        {
            "check": "scroll_plan",
            "inputs": values,
            "remaining_distance": remaining,
            "base_scroll_count": base_count,
            "safety_gestures": args.safety_gestures,
            "scroll_count": count,
            "calculation": "ceil(max(0, content_height - visible_height) / scroll_distance)",
            "decision": "accept",
            "suggested_action": "record_exactly_the_planned_gesture_batch_then_stop_before_inspection",
        },
        EXIT_PASS,
    )


def load_image(path_value: str) -> np.ndarray:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise CheckError(f"Image does not exist: {path}")
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise CheckError(f"Unable to decode image: {path}")
    return image


def crop_body(
    image: np.ndarray, top_crop: int, bottom_crop: int, x_margin: int
) -> np.ndarray:
    height, width = image.shape[:2]
    if min(top_crop, bottom_crop, x_margin) < 0:
        raise CheckError("Crop values must be non-negative")
    if top_crop + bottom_crop >= height:
        raise CheckError(
            f"Vertical crops remove the whole image: {top_crop}+{bottom_crop}>={height}"
        )
    if x_margin * 2 >= width:
        raise CheckError(f"Horizontal margins remove the whole image: {x_margin}*2>={width}")
    bottom = height - bottom_crop if bottom_crop else height
    right = width - x_margin if x_margin else width
    return image[top_crop:bottom, x_margin:right]


def image_metrics(image: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return {
        "near_black_ratio": round(float(np.count_nonzero(gray < 8) / gray.size), 6),
        "mean_luma": round(float(gray.mean()), 3),
        "std_luma": round(float(gray.std()), 3),
    }


def check_viewport(args: argparse.Namespace) -> int:
    screenshot = load_image(args.image)
    height, width = screenshot.shape[:2]
    visual = image_metrics(screenshot)
    base = {
        "check": "viewport",
        "image": str(Path(args.image).expanduser().resolve()),
        "dimensions": {"width": width, "height": height},
        "visual": visual,
    }
    if visual["near_black_ratio"] >= args.near_black_ratio or visual["mean_luma"] <= 8:
        return emit(
            {
                **base,
                "decision": "reject",
                "reason": "near_black_viewport",
                "suggested_action": "confirm_unlock_and_retry_once",
            },
            EXIT_FAIL,
        )
    return emit(
        {
            **base,
            "decision": "accept",
            "reason": "decodable_non_black_viewport",
            "suggested_action": "perform_one_quick_visual_glance_then_deliver",
        },
        EXIT_PASS,
    )


def normalized_gray(image: np.ndarray, max_width: int = 384) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] > max_width:
        scale = max_width / gray.shape[1]
        gray = cv2.resize(
            gray,
            (max_width, max(1, round(gray.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return cv2.GaussianBlur(gray, (5, 5), 0)


def dhash(gray: np.ndarray, hash_width: int = 32, hash_height: int = 32) -> np.ndarray:
    small = cv2.resize(
        gray,
        (hash_width + 1, hash_height),
        interpolation=cv2.INTER_AREA,
    )
    return small[:, 1:] > small[:, :-1]


def similarity_metrics(first: np.ndarray, second: np.ndarray) -> dict[str, float]:
    if first.shape != second.shape:
        raise CheckError(
            f"Image dimensions differ: {first.shape[1]}x{first.shape[0]} vs "
            f"{second.shape[1]}x{second.shape[0]}"
        )
    first_gray = normalized_gray(first)
    second_gray = normalized_gray(second)
    absolute = cv2.absdiff(first_gray, second_gray)
    pixel_similarity = 1.0 - float(absolute.mean() / 255.0)
    first_hash = dhash(first_gray)
    second_hash = dhash(second_gray)
    hash_similarity = 1.0 - float(np.count_nonzero(first_hash != second_hash) / first_hash.size)
    return {
        "pixel_similarity": round(pixel_similarity, 6),
        "dhash_similarity": round(hash_similarity, 6),
    }


def chrome_similarity_metrics(
    first: np.ndarray,
    second: np.ndarray,
    top_crop: int,
    x_margin: int,
) -> dict[str, float] | None:
    """Compare stable app chrome above the scroll body, excluding the status bar."""
    if first.shape != second.shape:
        raise CheckError(
            f"Image dimensions differ: {first.shape[1]}x{first.shape[0]} vs "
            f"{second.shape[1]}x{second.shape[0]}"
        )
    height, width = first.shape[:2]
    chrome_top = round(height * 0.04)
    chrome_bottom = min(int(top_crop), round(height * 0.25))
    minimum_height = max(80, round(height * 0.06))
    if chrome_bottom - chrome_top < minimum_height:
        return None
    if x_margin * 2 >= width:
        raise CheckError(f"Horizontal margins remove the whole image: {x_margin}*2>={width}")
    right = width - x_margin if x_margin else width
    return similarity_metrics(
        first[chrome_top:chrome_bottom, x_margin:right],
        second[chrome_top:chrome_bottom, x_margin:right],
    )


def bottom_chrome_similarity_metrics(
    first: np.ndarray,
    second: np.ndarray,
    bottom_crop: int,
    x_margin: int,
) -> dict[str, float] | None:
    """Compare fixed lower app chrome when the top chrome folds during scrolling."""
    if first.shape != second.shape:
        raise CheckError(
            f"Image dimensions differ: {first.shape[1]}x{first.shape[0]} vs "
            f"{second.shape[1]}x{second.shape[0]}"
        )
    height, width = first.shape[:2]
    requested_height = max(int(bottom_crop), round(height * 0.12))
    region_height = min(requested_height, round(height * 0.25))
    chrome_top = max(0, height - region_height)
    chrome_bottom = height - round(height * 0.015)
    minimum_height = max(80, round(height * 0.06))
    if chrome_bottom - chrome_top < minimum_height:
        return None
    if x_margin * 2 >= width:
        raise CheckError(f"Horizontal margins remove the whole image: {x_margin}*2>={width}")
    right = width - x_margin if x_margin else width
    return similarity_metrics(
        first[chrome_top:chrome_bottom, x_margin:right],
        second[chrome_top:chrome_bottom, x_margin:right],
    )


def parse_pair(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        match = PAIR_PATTERN.search(line)
        if match:
            values = match.groupdict()
            return {
                "pair": int(values["pair"]),
                "confidence": float(values["confidence"]),
                "consensus": float(values["consensus"]),
                "offset_px": int(values["offset"]),
                "overlap_px": int(values["overlap"]),
                "mode": values["mode"].strip(),
                "status": values["status"].strip(),
            }
    return None


def run_pair_diagnostics(args: argparse.Namespace) -> tuple[dict[str, Any] | None, str]:
    binary = args.stitcher or os.environ.get("SCREENSHOT_STITCHER_BIN")
    if not binary:
        raise CheckError(
            "screenshot-stitcher path is unavailable; source agent-device-env.sh or pass --stitcher"
        )
    binary_path = Path(binary).expanduser().resolve()
    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        raise CheckError(f"screenshot-stitcher is not executable: {binary_path}")
    with tempfile.TemporaryDirectory(prefix="probe-check-") as temp_dir:
        output = Path(temp_dir) / "pair.png"
        command = [
            str(binary_path),
            str(Path(args.previous).expanduser().resolve()),
            str(Path(args.probe).expanduser().resolve()),
            "-o",
            str(output),
            "--top-crop",
            str(args.top_crop),
            "--bottom-crop",
            str(args.bottom_crop),
            "--x-margin",
            str(args.x_margin),
        ]
        if args.template_height is not None:
            command.extend(["--template-height", str(args.template_height)])
        if args.threshold is not None:
            command.extend(["--threshold", str(args.threshold)])
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return parse_pair(result.stdout), result.stdout.strip()


def check_probe(args: argparse.Namespace) -> int:
    previous = load_image(args.previous)
    probe = load_image(args.probe)
    if previous.shape != probe.shape:
        raise CheckError(
            f"Image dimensions differ: {previous.shape[1]}x{previous.shape[0]} vs "
            f"{probe.shape[1]}x{probe.shape[0]}"
        )
    previous_body = crop_body(previous, args.top_crop, args.bottom_crop, args.x_margin)
    probe_body = crop_body(probe, args.top_crop, args.bottom_crop, args.x_margin)
    visual = image_metrics(probe_body)
    similarity = similarity_metrics(previous_body, probe_body)
    strict_duplicate = (
        similarity["pixel_similarity"] >= args.duplicate_pixel_similarity
        or (
            similarity["pixel_similarity"] >= args.duplicate_pixel_floor
            and similarity["dhash_similarity"] >= args.duplicate_hash_similarity
        )
    )
    fast_visual_duplicate = bool(
        args.mode == "fast"
        and similarity["pixel_similarity"] >= args.fast_duplicate_pixel_floor
        and similarity["dhash_similarity"] >= args.fast_duplicate_hash_similarity
    )
    duplicate = strict_duplicate or fast_visual_duplicate
    base = {
        "check": "probe",
        "mode": args.mode,
        "previous": str(Path(args.previous).expanduser().resolve()),
        "probe": str(Path(args.probe).expanduser().resolve()),
        "body_dimensions": {
            "width": int(probe_body.shape[1]),
            "height": int(probe_body.shape[0]),
        },
        "visual": visual,
        "similarity": similarity,
    }
    if visual["near_black_ratio"] >= args.near_black_ratio or visual["mean_luma"] <= 8:
        return emit(
            {
                **base,
                "decision": "reject",
                "reason": "near_black_probe",
                "suggested_action": "retry_capture",
            },
            EXIT_FAIL,
        )
    if duplicate:
        return emit(
            {
                **base,
                "decision": "reject",
                "reason": "duplicate_or_no_progress",
                "suggested_action": "exclude_probe_and_check_bottom",
            },
            EXIT_FAIL,
        )
    pair, raw_log = run_pair_diagnostics(args)
    if pair is None:
        return emit(
            {
                **base,
                "decision": "review",
                "reason": "overlap_diagnostics_unavailable",
                "diagnostic_log": raw_log[-2000:],
                "suggested_action": "inspect_probe_manually",
            },
            EXIT_REVIEW,
        )
    body_height = probe_body.shape[0]
    overlap_ratio = pair["overlap_px"] / body_height
    new_content_ratio = pair["offset_px"] / body_height
    pair = {
        **pair,
        "overlap_ratio": round(overlap_ratio, 6),
        "new_content_ratio": round(new_content_ratio, 6),
    }
    result = {**base, "pair": pair}
    if pair["offset_px"] <= max(args.min_shift_px, round(body_height * 0.01)):
        return emit(
            {
                **result,
                "decision": "reject",
                "reason": "no_vertical_progress",
                "suggested_action": "exclude_probe_and_check_bottom",
            },
            EXIT_FAIL,
        )
    minimum_overlap = (
        args.fast_min_overlap_ratio if args.mode == "fast" else args.min_overlap_ratio
    )
    if overlap_ratio < minimum_overlap:
        return emit(
            {
                **result,
                "decision": "review",
                "reason": "insufficient_overlap",
                "suggested_action": "recapture_with_a_shorter_scroll",
            },
            EXIT_REVIEW,
        )
    weak_overlap = (
        pair["mode"] != "matched"
        or pair["confidence"] < args.min_confidence
        or pair["consensus"] < args.min_consensus
    )
    if weak_overlap and args.mode == "verified":
        return emit(
            {
                **result,
                "decision": "review",
                "reason": "low_confidence_overlap",
                "suggested_action": "inspect_or_recapture_before_promoting",
            },
            EXIT_REVIEW,
        )
    if weak_overlap:
        return emit(
            {
                **result,
                "decision": "accept_with_warnings",
                "reason": "usable_progress_with_low_confidence_overlap",
                "warnings": ["fallback_or_low_confidence_overlap"],
                "suggested_action": "promote_probe_and_preserve_warning_for_final_spot_check",
            },
            EXIT_PASS,
        )
    return emit(
        {
            **result,
            "decision": "accept",
            "reason": "new_content_with_usable_overlap",
            "suggested_action": "promote_probe_to_next_segment",
        },
        EXIT_PASS,
    )


def parse_appstate_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CheckError(f"agent-device appstate returned invalid JSON: {error}") from error
    if not payload.get("success") or not isinstance(payload.get("data"), dict):
        raise CheckError(f"agent-device appstate failed: {text[:500]}")
    return payload["data"]


def check_target_app(args: argparse.Namespace) -> int:
    executable = args.agent_device or shutil.which("agent-device")
    if not executable:
        raise CheckError("agent-device is unavailable on PATH; source agent-device-env.sh")
    command = [executable, "appstate", "--session", args.session, "--json"]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CheckError(f"agent-device appstate failed: {result.stdout.strip()}")
    state = parse_appstate_json(result.stdout)
    # Android reports the foreground app as `package`; Apple platforms report
    # `appBundleId`. Accept either so identity checks compare a real value.
    reported_bundle = (
        state.get("package")
        or state.get("appPackage")
        or state.get("appBundleId")
        or state.get("appName")
    )
    source = state.get("source") or "unknown"
    expected_match = (
        None if args.expected_bundle is None else reported_bundle == args.expected_bundle
    )
    continuity = None
    chrome_continuity = None
    bottom_chrome_continuity = None
    if bool(args.before_screenshot) != bool(args.after_screenshot):
        raise CheckError("Pass both --before-screenshot and --after-screenshot, or neither")
    if args.before_screenshot and args.after_screenshot:
        if Path(args.before_screenshot).expanduser().resolve() == Path(
            args.after_screenshot
        ).expanduser().resolve():
            raise CheckError("Before and after screenshots must be distinct capture files")
        before = load_image(args.before_screenshot)
        after = load_image(args.after_screenshot)
        before_body = crop_body(before, args.top_crop, args.bottom_crop, args.x_margin)
        after_body = crop_body(after, args.top_crop, args.bottom_crop, args.x_margin)
        continuity = similarity_metrics(before_body, after_body)
        chrome_continuity = chrome_similarity_metrics(
            before,
            after,
            args.top_crop,
            args.x_margin,
        )
        bottom_chrome_continuity = bottom_chrome_similarity_metrics(
            before,
            after,
            args.bottom_crop,
            args.x_margin,
        )
    stable_top_chrome = bool(
        chrome_continuity
        and chrome_continuity["pixel_similarity"] >= args.min_chrome_similarity
        and chrome_continuity["dhash_similarity"] >= args.min_chrome_hash_similarity
    )
    stable_bottom_chrome = bool(
        bottom_chrome_continuity
        and bottom_chrome_continuity["pixel_similarity"] >= args.min_chrome_similarity
        and bottom_chrome_continuity["dhash_similarity"] >= args.min_chrome_hash_similarity
    )
    stable_chrome = bool(
        stable_top_chrome
        or (args.continuity_mode == "scrolled" and stable_bottom_chrome)
    )
    dynamic_body_plausible = bool(
        continuity
        and continuity["pixel_similarity"] >= args.min_dynamic_body_similarity
        and continuity["dhash_similarity"] >= args.min_dynamic_body_hash_similarity
    )
    base = {
        "check": "target_app",
        "session": args.session,
        "expected_bundle": args.expected_bundle,
        "reported_bundle": reported_bundle,
        "state_source": source,
        "state": state,
        "bundle_match": expected_match,
        "visual_continuity": continuity,
        "visual_identity": {
            "continuity_mode": args.continuity_mode,
            "chrome_continuity": chrome_continuity,
            "top_chrome_continuity": chrome_continuity,
            "bottom_chrome_continuity": bottom_chrome_continuity,
            "stable_top_chrome": stable_top_chrome,
            "stable_bottom_chrome": stable_bottom_chrome,
            "stable_chrome": stable_chrome,
            "stable_chrome_source": (
                "top"
                if stable_top_chrome
                else "bottom"
                if stable_bottom_chrome and args.continuity_mode == "scrolled"
                else None
            ),
            "dynamic_body_plausible": dynamic_body_plausible,
        },
    }
    if args.expected_bundle is not None and not expected_match:
        return emit(
            {
                **base,
                "decision": "reject",
                "reason": "target_bundle_mismatch",
                "suggested_action": "do_not_operate_the_reported_app",
            },
            EXIT_FAIL,
        )
    body_hard_change = bool(
        continuity
        and continuity["pixel_similarity"] < args.min_visual_similarity
        and continuity["dhash_similarity"] < args.min_visual_hash_similarity
    )
    body_ambiguous = bool(
        continuity
        and (
            continuity["pixel_similarity"] < args.min_visual_similarity
            or continuity["dhash_similarity"] < args.min_visual_hash_similarity
        )
    )
    stable_expected_identity = bool(
        args.expected_bundle is not None
        and expected_match
        and stable_chrome
        and (
            args.continuity_mode == "scrolled"
            or dynamic_body_plausible
        )
    )
    if body_ambiguous and stable_expected_identity:
        return emit(
            {
                **base,
                "decision": "accept_with_warnings",
                "reason": (
                    "stable_app_chrome_with_expected_scroll_progress"
                    if args.continuity_mode == "scrolled"
                    else "stable_app_chrome_with_dynamic_body"
                ),
                "verification_level": "bundle_and_stable_chrome",
                "warnings": ["scroll_body_changed_while_app_identity_remained_stable"],
                "suggested_action": "continue_with_the_verified_target_and_preserve_warning",
            },
            EXIT_PASS,
        )
    if body_hard_change:
        return emit(
            {
                **base,
                "decision": "reject",
                "reason": "unexpected_visual_change_during_read_only_observation",
                "suggested_action": "treat_as_stale_session_reactivation",
            },
            EXIT_FAIL,
        )
    if body_ambiguous:
        return emit(
            {
                **base,
                "decision": "review",
                "reason": "visual_continuity_is_ambiguous",
                "suggested_action": "inspect_the_pre_and_post_observation_screenshots",
            },
            EXIT_REVIEW,
        )
    if source == "session" and continuity is None:
        return emit(
            {
                **base,
                "decision": "review",
                "reason": "session_state_is_not_independent_foreground_proof",
                "suggested_action": "verify_with_pre_and_post_observation_screenshots",
            },
            EXIT_REVIEW,
        )
    if args.expected_bundle is None and continuity is None:
        return emit(
            {
                **base,
                "decision": "review",
                "reason": "no_expected_bundle_or_visual_continuity_evidence",
                "suggested_action": "capture_visual_continuity_evidence",
            },
            EXIT_REVIEW,
        )
    verification_level = "bundle_and_visual" if args.expected_bundle else "visual_continuity"
    return emit(
        {
            **base,
            "decision": "accept",
            "reason": "target_evidence_is_consistent",
            "verification_level": verification_level,
            "suggested_action": "continue_with_the_verified_target",
        },
        EXIT_PASS,
    )


def load_report(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise CheckError(f"Stitch report does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"Unable to read stitch report {path}: {error}") from error


def repeated_region_runs(
    image: np.ndarray,
    window_height: int,
    step: int,
    x_margin: int,
    min_std: float,
    min_correlation: float,
    max_mae: float,
    min_run_windows: int,
) -> list[dict[str, Any]]:
    height, width = image.shape[:2]
    if window_height <= 0 or step <= 0 or window_height > height:
        return []
    right = width - x_margin if x_margin else width
    gray = cv2.cvtColor(image[:, x_margin:right], cv2.COLOR_BGR2GRAY)
    scale = min(1.0, 256.0 / gray.shape[1])
    search = cv2.resize(
        gray,
        (max(1, round(gray.shape[1] * scale)), gray.shape[0]),
        interpolation=cv2.INTER_AREA,
    ).astype(np.float32)
    scaled_window = window_height
    scaled_step = step
    if scaled_window >= search.shape[0]:
        return []
    matches: list[dict[str, float | int]] = []
    source_index = 0
    for source_y in range(0, search.shape[0] - scaled_window + 1, scaled_step):
        template = search[source_y : source_y + scaled_window]
        search_start = source_y + scaled_window
        source_index += 1
        if float(template.std()) < min_std or search_start + scaled_window > search.shape[0]:
            continue
        result = cv2.matchTemplate(
            search[search_start:], template, cv2.TM_CCOEFF_NORMED
        )
        _, correlation, _, location = cv2.minMaxLoc(result)
        target_y = search_start + location[1]
        matched = search[target_y : target_y + scaled_window]
        mae = float(np.mean(np.abs(template - matched)) / 255.0)
        if correlation >= min_correlation and mae <= max_mae:
            matches.append(
                {
                    "source_index": source_index,
                    "source_y": source_y,
                    "target_y": target_y,
                    "delta": target_y - source_y,
                    "correlation": float(correlation),
                    "mae": mae,
                }
            )
    tolerance = max(4, scaled_step // 2)
    runs: list[list[dict[str, float | int]]] = []
    current: list[dict[str, float | int]] = []
    for match in matches:
        if current:
            previous = current[-1]
            consecutive = int(match["source_index"]) == int(previous["source_index"]) + 1
            consistent_delta = abs(int(match["delta"]) - int(previous["delta"])) <= tolerance
            if not (consecutive and consistent_delta):
                if len(current) >= min_run_windows:
                    runs.append(current)
                current = []
        current.append(match)
    if len(current) >= min_run_windows:
        runs.append(current)
    formatted: list[dict[str, Any]] = []
    for run in runs:
        first_start = int(run[0]["source_y"])
        first_end = int(run[-1]["source_y"]) + scaled_window
        second_start = int(run[0]["target_y"])
        second_end = int(run[-1]["target_y"]) + scaled_window
        formatted.append(
            {
                "first_range": [first_start, first_end],
                "second_range": [second_start, second_end],
                "separation_px": second_start - first_start,
                "run_windows": len(run),
                "mean_correlation": round(
                    float(np.mean([float(item["correlation"]) for item in run])), 6
                ),
                "mean_mae": round(
                    float(np.mean([float(item["mae"]) for item in run])), 6
                ),
            }
        )
    return formatted


def qa_stitched_output(args: argparse.Namespace) -> int:
    stitched = load_image(args.stitched)
    stitched_height, stitched_width = stitched.shape[:2]
    report = load_report(args.report) if args.report else None
    settings = report.get("settings", {}) if report else {}
    top_crop = args.top_crop if args.top_crop is not None else int(settings.get("top_crop", 0))
    bottom_crop = (
        args.bottom_crop if args.bottom_crop is not None else int(settings.get("bottom_crop", 0))
    )
    x_margin = args.x_margin if args.x_margin is not None else int(settings.get("x_margin", 0))
    segment_paths = list(args.segments or [])
    if not segment_paths and report:
        segment_paths = [item["path"] for item in report.get("inputs", []) if item.get("path")]
    segments = [load_image(path) for path in segment_paths]
    duplicate_inputs: list[dict[str, Any]] = []
    for index, (first, second) in enumerate(zip(segments, segments[1:]), start=1):
        first_body = crop_body(first, top_crop, bottom_crop, x_margin)
        second_body = crop_body(second, top_crop, bottom_crop, x_margin)
        metrics = similarity_metrics(first_body, second_body)
        if (
            metrics["pixel_similarity"] >= args.duplicate_pixel_similarity
            or (
                metrics["pixel_similarity"] >= args.duplicate_pixel_floor
                and metrics["dhash_similarity"] >= args.duplicate_hash_similarity
            )
        ):
            duplicate_inputs.append({"pair": index, **metrics})
    pairs = report.get("pairs", []) if report else []
    low_confidence_pairs = report.get("low_confidence_pair_numbers", []) if report else []
    expected_height = None
    height_delta = None
    height_delta_ratio = None
    if report and report.get("inputs") and len(pairs) == len(report["inputs"]) - 1:
        first_height = int(report["inputs"][0]["height"])
        expected_height = first_height + sum(int(pair["offset_px"]) for pair in pairs)
        height_delta = stitched_height - expected_height
        height_delta_ratio = height_delta / expected_height if expected_height else None
    window_height = args.repeat_window_height or max(300, min(600, round(stitched_height * 0.04)))
    step = args.repeat_step or max(100, window_height // 2)
    repeated_runs = repeated_region_runs(
        stitched,
        window_height=window_height,
        step=step,
        x_margin=max(0, x_margin),
        min_std=args.repeat_min_std,
        min_correlation=args.repeat_min_correlation,
        max_mae=args.repeat_max_mae,
        min_run_windows=args.repeat_min_run_windows,
    )
    base = {
        "check": "stitched_output",
        "mode": args.mode,
        "stitched": str(Path(args.stitched).expanduser().resolve()),
        "dimensions": {"width": stitched_width, "height": stitched_height},
        "visual": image_metrics(stitched),
        "report": str(Path(args.report).expanduser().resolve()) if args.report else None,
        "segment_count": len(segments),
        "duplicate_input_pairs": duplicate_inputs,
        "low_confidence_pairs": low_confidence_pairs,
        "expected_height_from_offsets": expected_height,
        "height_delta_px": height_delta,
        "height_delta_ratio": round(height_delta_ratio, 6) if height_delta_ratio is not None else None,
        "repeated_region_runs": repeated_runs,
        "repeat_scan": {
            "window_height": window_height,
            "step": step,
        },
    }
    hard_reasons: list[str] = []
    review_reasons: list[str] = []
    if base["visual"]["near_black_ratio"] >= args.near_black_ratio or base["visual"]["mean_luma"] <= 8:
        hard_reasons.append("near_black_stitched_output")
    if args.mode == "fast":
        if duplicate_inputs:
            review_reasons.append("duplicate_input_segments")
        if height_delta_ratio is not None:
            if abs(height_delta_ratio) > args.fast_max_height_error_ratio:
                hard_reasons.append("gross_stitched_height_inconsistency")
            elif abs(height_delta_ratio) > args.review_height_error_ratio:
                review_reasons.append("stitched_height_needs_review")
        if repeated_runs:
            review_reasons.append("large_repeated_regions_detected")
        if low_confidence_pairs:
            review_reasons.append("low_confidence_seams")
        if report is None and not args.allow_missing_report:
            review_reasons.append("missing_stitch_report")
    else:
        if duplicate_inputs:
            hard_reasons.append("duplicate_input_segments")
        if height_delta_ratio is not None:
            if abs(height_delta_ratio) > args.max_height_error_ratio:
                hard_reasons.append("stitched_height_inconsistent_with_pair_offsets")
            elif abs(height_delta_ratio) > args.review_height_error_ratio:
                review_reasons.append("stitched_height_needs_review")
        if repeated_runs:
            hard_reasons.append("large_repeated_regions_detected")
        if low_confidence_pairs:
            review_reasons.append("low_confidence_seams")
        if report is None and not args.allow_missing_report:
            review_reasons.append("missing_stitch_report")
    if hard_reasons:
        return emit(
            {
                **base,
                "decision": "reject",
                "reasons": hard_reasons + review_reasons,
                "suggested_action": "do_not_deliver; retry_capture_or_restitch",
            },
            EXIT_FAIL,
        )
    if review_reasons:
        if args.mode == "fast":
            return emit(
                {
                    **base,
                    "decision": "accept_with_warnings",
                    "reasons": review_reasons,
                    "suggested_action": "perform_one_quick_top_bottom_order_spot_check_then_deliver",
                },
                EXIT_PASS,
            )
        return emit(
            {
                **base,
                "decision": "review",
                "reasons": review_reasons,
                "suggested_action": "inspect_flagged_seams_before_delivery",
            },
            EXIT_REVIEW,
        )
    return emit(
        {
            **base,
            "decision": "accept",
            "reasons": [],
            "suggested_action": "perform_final_visual_spot_check_then_deliver",
        },
        EXIT_PASS,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic checks for Agent Device screenshot workflows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scroll_plan = subparsers.add_parser(
        "scroll-plan", help="Calculate a bounded-page scroll count with ceiling division"
    )
    scroll_plan.add_argument("--content-height", type=float, required=True)
    scroll_plan.add_argument("--visible-height", type=float, required=True)
    scroll_plan.add_argument("--scroll-distance", type=float, required=True)
    scroll_plan.add_argument("--safety-gestures", type=int, default=0)
    scroll_plan.set_defaults(handler=plan_scroll_count)

    viewport = subparsers.add_parser(
        "viewport", help="Run the lightweight normal-screenshot integrity check"
    )
    viewport.add_argument("--image", required=True)
    viewport.add_argument("--near-black-ratio", type=float, default=0.85)
    viewport.set_defaults(handler=check_viewport)

    probe = subparsers.add_parser("probe", help="Validate a provisional long-screenshot frame")
    probe.add_argument("--mode", choices=("fast", "verified"), default="fast")
    probe.add_argument("--previous", required=True)
    probe.add_argument("--probe", required=True)
    probe.add_argument("--top-crop", type=int, default=0)
    probe.add_argument("--bottom-crop", type=int, default=0)
    probe.add_argument("--x-margin", type=int, default=0)
    probe.add_argument("--stitcher")
    probe.add_argument("--template-height", type=int)
    probe.add_argument("--threshold", type=float)
    probe.add_argument("--near-black-ratio", type=float, default=0.85)
    probe.add_argument("--duplicate-pixel-similarity", type=float, default=0.995)
    probe.add_argument("--duplicate-pixel-floor", type=float, default=0.98)
    probe.add_argument("--duplicate-hash-similarity", type=float, default=0.995)
    probe.add_argument("--fast-duplicate-pixel-floor", type=float, default=0.985)
    probe.add_argument("--fast-duplicate-hash-similarity", type=float, default=0.95)
    probe.add_argument("--min-shift-px", type=int, default=8)
    probe.add_argument("--min-overlap-ratio", type=float, default=0.20)
    probe.add_argument("--fast-min-overlap-ratio", type=float, default=0.08)
    probe.add_argument("--min-confidence", type=float, default=0.50)
    probe.add_argument("--min-consensus", type=float, default=0.20)
    probe.set_defaults(handler=check_probe)

    target = subparsers.add_parser("target-app", help="Check target-app consistency")
    target.add_argument("--expected-bundle")
    target.add_argument("--session", default=os.environ.get("AGENT_DEVICE_SESSION", "phone-main"))
    target.add_argument("--agent-device")
    target.add_argument("--before-screenshot")
    target.add_argument("--after-screenshot")
    target.add_argument("--top-crop", type=int, default=0)
    target.add_argument("--bottom-crop", type=int, default=0)
    target.add_argument("--x-margin", type=int, default=0)
    target.add_argument("--min-visual-similarity", type=float, default=0.97)
    target.add_argument("--min-visual-hash-similarity", type=float, default=0.90)
    target.add_argument("--min-chrome-similarity", type=float, default=0.97)
    target.add_argument("--min-chrome-hash-similarity", type=float, default=0.90)
    target.add_argument("--min-dynamic-body-similarity", type=float, default=0.84)
    target.add_argument("--min-dynamic-body-hash-similarity", type=float, default=0.70)
    target.add_argument(
        "--continuity-mode",
        choices=("read-only", "scrolled"),
        default="read-only",
    )
    target.set_defaults(handler=check_target_app)

    stitched = subparsers.add_parser("stitched", help="QA a stitched long screenshot")
    stitched.add_argument("--mode", choices=("fast", "verified"), default="fast")
    stitched.add_argument("--stitched", required=True)
    stitched.add_argument("--report")
    stitched.add_argument("--segments", nargs="+")
    stitched.add_argument("--top-crop", type=int)
    stitched.add_argument("--bottom-crop", type=int)
    stitched.add_argument("--x-margin", type=int)
    stitched.add_argument("--duplicate-pixel-similarity", type=float, default=0.995)
    stitched.add_argument("--duplicate-pixel-floor", type=float, default=0.98)
    stitched.add_argument("--duplicate-hash-similarity", type=float, default=0.995)
    stitched.add_argument("--review-height-error-ratio", type=float, default=0.02)
    stitched.add_argument("--max-height-error-ratio", type=float, default=0.05)
    stitched.add_argument("--fast-max-height-error-ratio", type=float, default=0.15)
    stitched.add_argument("--near-black-ratio", type=float, default=0.85)
    stitched.add_argument("--repeat-window-height", type=int)
    stitched.add_argument("--repeat-step", type=int)
    stitched.add_argument("--repeat-min-std", type=float, default=12.0)
    stitched.add_argument("--repeat-min-correlation", type=float, default=0.995)
    stitched.add_argument("--repeat-max-mae", type=float, default=0.03)
    stitched.add_argument("--repeat-min-run-windows", type=int, default=3)
    stitched.add_argument("--allow-missing-report", action="store_true")
    stitched.set_defaults(handler=qa_stitched_output)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except CheckError as error:
        return emit(
            {
                "check": args.command,
                "decision": "error",
                "reason": str(error),
            },
            EXIT_ERROR,
        )


if __name__ == "__main__":
    raise SystemExit(main())
