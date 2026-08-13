#!/usr/bin/env python3
"""Validate and stitch ordered physical-iPhone screenshots locally."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import cv2
import numpy as np


PROFILES = {
    "generic": {},
    "airbnb": {"top_crop": 240, "bottom_crop": 492, "x_margin": 40},
}

PAIR_PATTERN = re.compile(
    r"Pair (?P<pair>\d+): confidence=(?P<confidence>[0-9.]+), "
    r"consensus=(?P<consensus>[0-9.]+), offset=(?P<offset>\d+)px, "
    r"overlap=(?P<overlap>\d+)px, mode=(?P<mode>[^,]+), "
    r"(?P<status>.*)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and stitch ordered iPhone screenshots with screenshot-stitcher."
    )
    parser.add_argument("images", nargs="+", help="Ordered PNG screenshots from one iPhone.")
    parser.add_argument("-o", "--output", required=True, help="Output PNG path.")
    parser.add_argument(
        "--profile", choices=sorted(PROFILES), default="generic", help="App chrome profile."
    )
    parser.add_argument("--top-crop", type=int, help="Override profile top crop in pixels.")
    parser.add_argument("--bottom-crop", type=int, help="Override profile bottom crop in pixels.")
    parser.add_argument("--x-margin", type=int, help="Override horizontal matching margin.")
    parser.add_argument("--template-height", type=int, help="Override overlap template height.")
    parser.add_argument("--threshold", type=float, help="Override overlap acceptance threshold.")
    parser.add_argument(
        "--qa-confidence",
        type=float,
        default=0.5,
        help="Flag matched pairs below this confidence for visual QA (default: 0.5).",
    )
    parser.add_argument("--log", help="Diagnostic log path; defaults beside the output.")
    parser.add_argument("--report", help="JSON report path; defaults beside the output.")
    return parser.parse_args()


def load_inputs(paths: list[Path]) -> tuple[tuple[int, int], list[dict[str, object]], list[str]]:
    dimensions: tuple[int, int] | None = None
    metrics: list[dict[str, object]] = []
    warnings: list[str] = []

    for path in paths:
        if not path.is_file():
            raise ValueError(f"Input does not exist: {path}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Unable to decode image: {path}")
        height, width = image.shape[:2]
        current_dimensions = (width, height)
        if dimensions is None:
            dimensions = current_dimensions
        elif current_dimensions != dimensions:
            raise ValueError(
                f"Input dimensions differ: expected {dimensions[0]}x{dimensions[1]}, "
                f"got {width}x{height} for {path}"
            )

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        near_black_ratio = float(np.count_nonzero(gray < 8) / gray.size)
        mean_luma = float(gray.mean())
        if near_black_ratio >= 0.85 or mean_luma <= 8:
            raise ValueError(
                f"Rejected near-black capture: {path} "
                f"(black={near_black_ratio:.1%}, luma={mean_luma:.1f})"
            )
        if near_black_ratio >= 0.20:
            warnings.append(
                f"Large dark region in {path.name}: {near_black_ratio:.1%}; inspect its seams."
            )
        metrics.append(
            {
                "path": str(path),
                "width": width,
                "height": height,
                "near_black_ratio": round(near_black_ratio, 5),
                "mean_luma": round(mean_luma, 2),
            }
        )

    if dimensions is None:
        raise ValueError("No input images supplied")
    return dimensions, metrics, warnings


def resolve_settings(args: argparse.Namespace) -> dict[str, int | float | None]:
    settings: dict[str, int | float | None] = dict(PROFILES[args.profile])
    for key in ("top_crop", "bottom_crop", "x_margin", "template_height", "threshold"):
        value = getattr(args, key)
        if value is not None:
            settings[key] = value
    return settings


def build_command(
    binary: str, images: list[Path], output: Path, settings: dict[str, int | float | None]
) -> list[str]:
    command = [binary, *(str(path) for path in images), "-o", str(output)]
    option_names = {
        "top_crop": "--top-crop",
        "bottom_crop": "--bottom-crop",
        "x_margin": "--x-margin",
        "template_height": "--template-height",
        "threshold": "--threshold",
    }
    for key, option in option_names.items():
        value = settings.get(key)
        if value is not None:
            command.extend([option, str(value)])
    return command


def parse_pairs(log_text: str) -> list[dict[str, object]]:
    pairs: list[dict[str, object]] = []
    for line in log_text.splitlines():
        match = PAIR_PATTERN.search(line)
        if not match:
            continue
        values = match.groupdict()
        pairs.append(
            {
                "pair": int(values["pair"]),
                "confidence": float(values["confidence"]),
                "consensus": float(values["consensus"]),
                "offset_px": int(values["offset"]),
                "overlap_px": int(values["overlap"]),
                "mode": values["mode"].strip(),
                "status": values["status"].strip(),
            }
        )
    return pairs


def main() -> int:
    args = parse_args()
    if len(args.images) < 2:
        print("At least two screenshots are required.", file=sys.stderr)
        return 2

    images = [Path(path).expanduser().resolve() for path in args.images]
    output = Path(args.output).expanduser().resolve()
    log_path = (
        Path(args.log).expanduser().resolve()
        if args.log
        else output.with_suffix(output.suffix + ".stitch.log")
    )
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else output.with_suffix(output.suffix + ".stitch.json")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        dimensions, input_metrics, warnings = load_inputs(images)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    settings = resolve_settings(args)
    binary = os.environ.get("SCREENSHOT_STITCHER_BIN") or shutil.which("screenshot-stitcher")
    if not binary or not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        print(f"screenshot-stitcher binary is unavailable: {binary}", file=sys.stderr)
        return 2

    command = build_command(binary, images, output, settings)
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.write_text(result.stdout, encoding="utf-8")
    print(result.stdout, end="")
    if result.returncode != 0 or not output.is_file():
        print(f"Stitching failed; see {log_path}", file=sys.stderr)
        return result.returncode or 1

    stitched = cv2.imread(str(output), cv2.IMREAD_COLOR)
    if stitched is None:
        print(f"Unable to decode stitched output: {output}", file=sys.stderr)
        return 1
    output_height, output_width = stitched.shape[:2]
    if output_width != dimensions[0]:
        print(
            f"Unexpected output width: {output_width}; expected {dimensions[0]}", file=sys.stderr
        )
        return 1

    pairs = parse_pairs(result.stdout)
    low_confidence_pairs = [
        pair
        for pair in pairs
        if pair["mode"] != "matched" or float(pair["confidence"]) < args.qa_confidence
    ]
    if len(pairs) != len(images) - 1:
        warnings.append(
            f"Expected {len(images) - 1} pair diagnostics but parsed {len(pairs)}."
        )
    qa_required = bool(warnings or low_confidence_pairs)
    report = {
        "tool": "screenshot-stitcher",
        "tool_version": "0.1.0",
        "profile": args.profile,
        "settings": settings,
        "output": str(output),
        "output_width": output_width,
        "output_height": output_height,
        "inputs": input_metrics,
        "pairs": pairs,
        "low_confidence_pair_numbers": [pair["pair"] for pair in low_confidence_pairs],
        "warnings": warnings,
        "visual_qa_required": qa_required,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for warning in warnings:
        print(f"WARNING: {warning}")
    print(f"STITCH_RESULT={output}")
    print(f"STITCH_LOG={log_path}")
    print(f"STITCH_REPORT={report_path}")
    print(f"STITCH_QA_REQUIRED={'yes' if qa_required else 'no'}")
    if low_confidence_pairs:
        pair_numbers = ",".join(str(pair["pair"]) for pair in low_confidence_pairs)
        print(f"STITCH_QA_PAIRS={pair_numbers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
