#!/usr/bin/env python3
"""Run the bounded fast long-screenshot pipeline after target-app visual verification."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import time
from typing import Any, Callable, TypeVar

import cv2


EXIT_PASS = 0
EXIT_FAIL = 10
EXIT_ERROR = 2
DEFAULT_SOFT_VIEWPORTS = 4.0
DEFAULT_HARD_VIEWPORTS = 6.0


def optional_positive_environment_number(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive number") from error
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


CONFIGURED_VIEWPORT_WIDTH = optional_positive_environment_number("CSI_VIEWPORT_WIDTH")
CONFIGURED_VIEWPORT_HEIGHT = optional_positive_environment_number("CSI_VIEWPORT_HEIGHT")
T = TypeVar("T")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hash_skill_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if any(part in {"__pycache__", ".DS_Store"} for part in path.parts):
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def detect_variant(skill_root: Path) -> str:
    return "candidate" if "candidates" in skill_root.parts else "baseline"


def classify_failure(stage: str, reason: str) -> str:
    text = f"{stage} {reason}".lower()
    if "runtime safety cap" in text or "runtime limit" in text:
        return "RUNTIME_LIMIT"
    if "target" in text and any(token in text for token in ("continuity", "bundle", "wrong", "stale")):
        return "TARGET_CONTINUITY"
    if stage == "recording":
        return "RECORDING_FAILED"
    if stage == "sequence_selection":
        return "SEQUENCE_COVERAGE"
    if stage == "continuity_capture":
        return "CAPTURE_CONTINUITY"
    if stage == "adaptive_still_capture":
        return "ADAPTIVE_GESTURE"
    if stage in {"stitch", "qa", "stitch_retry", "qa_retry", "adaptive_still_stitch", "adaptive_still_qa"}:
        return "STITCH_QA"
    if stage == "snapshot_and_plan":
        if "0x0" in text or "0×0" in text or "zero-sized" in text:
            return "SNAPSHOT_ZERO_ROOT"
        if "not at the top" in text or "not at top" in text:
            return "SNAPSHOT_NOT_TOP"
        return "SNAPSHOT_NO_CONTAINER"
    if "near-black" in text or "near black" in text:
        return "VIEWPORT_NEAR_BLACK"
    if "no progress" in text or "no_visual_progress" in text:
        return "SCROLL_NO_PROGRESS"
    if "recording" in text:
        return "RECORDING_FAILED"
    if "sequence" in text or "coverage" in text:
        return "SEQUENCE_COVERAGE"
    if "continuity" in text:
        return "CAPTURE_CONTINUITY"
    if "stitch" in text or "seam" in text:
        return "STITCH_QA"
    return "UNKNOWN"


def build_viewport_evidence_pack(work_dir: Path, state: dict[str, Any]) -> Path | None:
    """Preserve ordered, decodable, non-black source viewports after a hard failure."""
    if not state.get("target_verified"):
        return None
    candidates: list[Path] = []
    for raw_path in state.get("segment_paths") or []:
        candidates.append(Path(raw_path))
    candidates.extend(sorted((work_dir / "accepted").glob("segment-*.png")))
    candidates.extend([work_dir / "segment-000.png", work_dir / "bottom.png"])
    seen: set[str] = set()
    evidence: list[dict[str, Any]] = []
    for path in candidates:
        path = path.expanduser().resolve()
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        near_black_ratio = float((gray < 8).mean())
        mean_luma = float(gray.mean())
        if near_black_ratio >= 0.85 or mean_luma <= 8:
            continue
        evidence.append(
            {
                "evidence_id": f"viewport-{len(evidence) + 1:03d}",
                "path": str(path),
                "capture_order": len(evidence) + 1,
                "classification": "Supporting",
                "sha256": digest,
                "dimensions": {"width": int(image.shape[1]), "height": int(image.shape[0])},
                "quality": {
                    "hard_pass": True,
                    "near_black_ratio": round(near_black_ratio, 6),
                    "mean_luma": round(mean_luma, 3),
                },
            }
        )
    if not evidence:
        return None
    geometry = state.get("geometry") or {}
    payload = {
        "schema_version": 1,
        "pack_id": f"{state.get('run_id', 'run')}-viewport-pack",
        "run_id": state.get("run_id"),
        "case_id": state.get("case_id"),
        "created_at": utc_now(),
        "expected_bundle": state.get("expected_bundle"),
        "capture_strategy": state.get("capture_strategy"),
        "page_complete": False,
        "stop_reason": state.get("failure", {}).get("code") if state.get("failure") else state.get("stop_reason"),
        "failed_stage": state.get("current_stage"),
        "crops": geometry.get("crops") or geometry.get("continuity_crops"),
        "evidence": evidence,
    }
    pack_path = work_dir / "evidence-pack.json"
    atomic_write_json(pack_path, payload)
    return pack_path


def evidence_pack_fallback_entry(state: dict[str, Any], stage: str) -> dict[str, Any]:
    endpoint_recovered = bool(
        (state.get("recording_recovery") or {}).get("outcome") == "pass"
    )
    return {
        "fallback_id": f"fallback-{len(state.get('fallback_chain') or []) + 1:03d}",
        "from_stage": stage,
        "to_strategy": (
            "target_verified_endpoint_evidence_pack"
            if endpoint_recovered
            else "ordered_viewport_evidence_pack"
        ),
        "changed_condition": (
            "recorder state was lost; preserve a fresh target-verified endpoint instead of retrying recording"
            if endpoint_recovered
            else "stop composite repair and preserve hard-quality source viewports"
        ),
        "expected_signal": "readable ordered evidence despite composite failure",
    }


class PipelineError(ValueError):
    def __init__(self, message: str, exit_code: int = EXIT_FAIL) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class RuntimeLimitError(PipelineError):
    """Signal that the run exhausted its user-approved wall-clock budget."""


class SemanticFallbackRequired(PipelineError):
    """Signal a semantic failure that can safely use visual coordinate scrolling."""

    def __init__(self, trigger: str, message: str) -> None:
        super().__init__(message)
        self.trigger = trigger


def is_semantic_snapshot_timeout(error: PipelineError) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "timed out",
            "time out",
            "timeout",
            "xctest snapshot timeout",
        )
    )


def is_recording_transport_failure(error: PipelineError) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "failed to stop recording",
            "not finalized into a playable video",
            "no active recording",
        )
    )


def parse_capture_extent(value: str) -> tuple[str, float | None]:
    normalized = str(value).strip().lower()
    if normalized in {"auto", "full"}:
        return normalized, None
    try:
        viewports = float(normalized)
    except ValueError as error:
        raise PipelineError(
            "--capture-extent must be auto, full, or a positive viewport count",
            EXIT_ERROR,
        ) from error
    if not math.isfinite(viewports) or viewports < 1.0:
        raise PipelineError(
            "--capture-extent viewport count must be finite and at least 1",
            EXIT_ERROR,
        )
    return "viewports", viewports


def build_capture_extent_policy(
    capture_extent: str,
    geometry: dict[str, Any],
    frame_height_px: int,
) -> dict[str, Any]:
    if frame_height_px <= 0:
        raise PipelineError("Initial screenshot height must be positive", EXIT_ERROR)
    mode, approved_viewports = parse_capture_extent(capture_extent)
    original_progress = float(geometry["required_progress_px"])
    bounded = geometry.get("height_confidence") == "bounded"
    estimated_page_viewports = (
        (frame_height_px + original_progress) / frame_height_px if bounded else None
    )

    target_progress: float | None
    hard_progress: float | None
    hard_limit_viewports: float | None
    page_complete_expected: bool | None
    limit_stop_reason: str | None

    if mode == "full":
        target_progress = original_progress if bounded else None
        hard_progress = None
        hard_limit_viewports = None
        page_complete_expected = True if bounded else None
        limit_stop_reason = None
    elif mode == "viewports":
        assert approved_viewports is not None
        approved_progress = max(0.0, (approved_viewports - 1.0) * frame_height_px)
        target_progress = (
            min(original_progress, approved_progress) if bounded else approved_progress
        )
        hard_progress = None
        hard_limit_viewports = None
        page_complete_expected = (
            original_progress <= approved_progress if bounded else None
        )
        limit_stop_reason = (
            None if page_complete_expected else "user_approved_limit_reached"
        )
    else:
        soft_progress = (DEFAULT_SOFT_VIEWPORTS - 1.0) * frame_height_px
        hard_progress = (DEFAULT_HARD_VIEWPORTS - 1.0) * frame_height_px
        hard_limit_viewports = DEFAULT_HARD_VIEWPORTS
        if (
            bounded
            and estimated_page_viewports is not None
            and estimated_page_viewports <= DEFAULT_HARD_VIEWPORTS
        ):
            target_progress = original_progress
            page_complete_expected = True
            limit_stop_reason = None
        else:
            target_progress = soft_progress
            page_complete_expected = False if bounded else None
            limit_stop_reason = "soft_viewport_limit_reached"

    if target_progress is None:
        capture_progress = original_progress
    elif bounded:
        capture_progress = min(original_progress, target_progress)
    else:
        capture_progress = target_progress
    target_viewports = (
        None
        if target_progress is None
        else 1.0 + max(0.0, target_progress) / frame_height_px
    )
    return {
        "requested": str(capture_extent).strip().lower(),
        "mode": mode,
        "soft_limit_viewports": DEFAULT_SOFT_VIEWPORTS if mode == "auto" else None,
        "hard_limit_viewports": hard_limit_viewports,
        "approved_viewports": approved_viewports,
        "estimated_page_viewports": (
            round(estimated_page_viewports, 3)
            if estimated_page_viewports is not None
            else None
        ),
        "target_viewports": (
            round(target_viewports, 3) if target_viewports is not None else None
        ),
        "original_required_progress_px": round(original_progress, 3),
        "capture_required_progress_px": (
            round(capture_progress, 3) if capture_progress is not None else None
        ),
        "target_progress_px": (
            round(target_progress, 3) if target_progress is not None else None
        ),
        "hard_progress_px": (
            round(hard_progress, 3) if hard_progress is not None else None
        ),
        "page_complete_expected": page_complete_expected,
        "limit_stop_reason": limit_stop_reason,
    }


def parse_json_output(text: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        start = text.find("{")
        if start < 0:
            raise PipelineError(f"{label} returned no JSON: {text[-1500:]}") from error
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError as nested:
            raise PipelineError(f"{label} returned invalid JSON: {text[-1500:]}") from nested
    if not isinstance(payload, dict):
        raise PipelineError(f"{label} returned a non-object JSON value")
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_command(
    command: list[str],
    label: str,
    allowed: tuple[int, ...] = (0,),
    log_path: Path | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, _ = process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, _ = process.communicate()
        timeout_note = (
            f"\n{label} stopped at the runtime safety cap "
            f"({float(timeout_seconds or 0):.3f}s remaining).\n"
        )
        stdout = (stdout or "") + timeout_note
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(stdout, encoding="utf-8")
        raise RuntimeLimitError(
            f"Runtime safety cap reached while waiting for {label}"
        ) from error
    result = subprocess.CompletedProcess(command, process.returncode, stdout or "", None)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result.stdout, encoding="utf-8")
    if result.returncode not in allowed:
        raise PipelineError(
            f"{label} failed with exit {result.returncode}: {result.stdout[-2000:]}"
        )
    return result


def rect(node: dict[str, Any]) -> dict[str, float]:
    value = node.get("rect") or {}
    return {
        "x": float(value.get("x", 0.0)),
        "y": float(value.get("y", 0.0)),
        "width": float(value.get("width", 0.0)),
        "height": float(value.get("height", 0.0)),
    }


def centered_gesture_x(
    root_rect: dict[str, float],
    scroll_rect: dict[str, float],
) -> int:
    """Choose the horizontal center shared by the app and scroll container."""
    left = max(root_rect["x"], scroll_rect["x"])
    right = min(
        root_rect["x"] + root_rect["width"],
        scroll_rect["x"] + scroll_rect["width"],
    )
    if right <= left:
        raise PipelineError("Scroll container does not overlap the app viewport")
    return round((left + right) / 2.0)


def node_bottom(node: dict[str, Any]) -> float:
    value = rect(node)
    return value["y"] + value["height"]


def percentage(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"(-?[0-9]+(?:\.[0-9]+)?)\s*%", value)
    return float(match.group(1)) if match else None


def semantic_page_count(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    for pattern in (
        r"([0-9]+(?:\.[0-9]+)?)\s*页",
        r"([0-9]+(?:\.[0-9]+)?)\s*pages?\b",
    ):
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            count = float(match.group(1))
            return count if 1.0 <= count <= 50.0 else None
    return None


def semantic_result_count(value: Any) -> int | None:
    """Extract a large result total without treating it as rendered content height."""
    if not isinstance(value, str):
        return None
    normalized = value.replace(",", "")
    patterns = (
        r"\b([0-9]+)\s+(?:flights?|results?|properties|hotels?|items?|matches|options)\b",
        r"\b(?:results?|properties|hotels?|items?|matches|options)\s*[:：]?\s*([0-9]+)\b",
        r"([0-9]+)\s*(?:个)?(?:结果|航班|住宿|酒店|项目|选项)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            count = int(match.group(1))
            return count if count > 0 else None
    return None


def is_vertical_scrollbar(node: dict[str, Any]) -> bool:
    label = str(node.get("label") or "").lower()
    return "垂直滚动条" in label or "vertical scroll bar" in label


def looks_like_media_region(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9]+\s*/\s*[0-9]+\+?", text):
        return True
    return any(
        token in text
        for token in ("照片", "图片", "图库", "photo", "image", "gallery", "carousel")
    )


def is_horizontal_scrollbar(node: dict[str, Any]) -> bool:
    label = str(node.get("label") or "").lower()
    return "水平滚动条" in label or "horizontal scroll bar" in label


def is_business_content_label(node: dict[str, Any]) -> bool:
    """Return true for readable page content, excluding media and scroll chrome."""
    if node.get("type") in {"Image", "Button"}:
        return False
    label = str(node.get("label") or "").strip()
    if len(label) < 4 or looks_like_media_region(label):
        return False
    lowered = label.lower()
    if is_vertical_scrollbar(node) or is_horizontal_scrollbar(node):
        return False
    if re.fullmatch(r"[0-9]+\s*(?:/|of)\s*[0-9]+\+?", lowered):
        return False
    return bool(re.search(r"[A-Za-z\u3400-\u9fff]", label))


def derive_scroll_plan(
    snapshot: dict[str, Any],
    pixel_width: int,
    pixel_height: int,
    scroll_distance_override: float | None,
    top_crop_override: int | None,
    bottom_crop_override: int | None,
    x_margin_override: int | None,
    gesture_x_override: int | None,
    gesture_y_override: int | None,
) -> dict[str, Any]:
    data = snapshot.get("data") or {}
    nodes = data.get("nodes") or []
    if not nodes:
        raise SemanticFallbackRequired(
            "no_nodes",
            "Semantic snapshot contains no nodes",
        )
    indexed = {int(node.get("index", position)): node for position, node in enumerate(nodes)}
    roots = [node for node in nodes if node.get("type") == "Application"]
    root = max(roots or nodes[:1], key=lambda item: rect(item)["width"] * rect(item)["height"])
    root_index = int(root.get("index", 0))
    root_rect = rect(root)
    if root_rect["width"] <= 0 or root_rect["height"] <= 0:
        raise SemanticFallbackRequired(
            "invalid_root_dimensions",
            "Semantic snapshot has invalid root dimensions",
        )

    children: dict[int, list[int]] = {}
    for node in nodes:
        if "parentIndex" in node:
            children.setdefault(int(node["parentIndex"]), []).append(int(node.get("index", 0)))

    def descendants(index: int) -> set[int]:
        result: set[int] = set()
        stack = list(children.get(index, []))
        while stack:
            current = stack.pop()
            if current in result:
                continue
            result.add(current)
            stack.extend(children.get(current, []))
        return result

    def ancestors(index: int) -> set[int]:
        result: set[int] = set()
        current = indexed.get(index)
        while current and "parentIndex" in current:
            parent = int(current["parentIndex"])
            if parent in result:
                break
            result.add(parent)
            current = indexed.get(parent)
        return result

    scroll_candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    all_candidate_diagnostics: list[dict[str, Any]] = []
    for node in nodes:
        value = rect(node)
        width_ratio = value["width"] / root_rect["width"]
        height_ratio = value["height"] / root_rect["height"]
        node_type = node.get("type")
        if node_type not in {"ScrollView", "Table", "CollectionView"}:
            continue
        if width_ratio < 0.70 or height_ratio < 0.35:
            continue
        candidate_index = int(node.get("index", 0))
        candidate_descendants = [
            indexed[index] for index in descendants(candidate_index) if index in indexed
        ]
        vertical_evidence = [
            item
            for item in candidate_descendants
            if is_vertical_scrollbar(item) and rect(item)["height"] >= value["height"] * 0.45
        ]
        identifier = str(node.get("identifier") or "").lower()
        identifier_hint = any(
            token in identifier for token in ("container", "details", "detail", "list", "home")
        )
        direct_cells = [
            indexed[index]
            for index in children.get(candidate_index, [])
            if index in indexed and indexed[index].get("type") == "Cell"
        ]
        cell_centers = [
            rect(item)["y"] + rect(item)["height"] / 2.0
            for item in direct_cells
            if rect(item)["height"] > 0
        ]
        vertical_cell_span = (
            max(cell_centers) - min(cell_centers) if len(cell_centers) >= 2 else 0.0
        )
        vertical_cell_evidence = bool(
            len(direct_cells) >= 2 and vertical_cell_span >= value["height"] * 0.12
        )
        collection_has_vertical_structure = bool(
            height_ratio >= 0.60
            and (vertical_evidence or vertical_cell_evidence or identifier_hint)
        )
        business_cells: list[dict[str, Any]] = []
        media_cells: list[dict[str, Any]] = []
        business_label_count = 0
        media_descendant_count = 0
        for cell in direct_cells:
            cell_index = int(cell.get("index", 0))
            cell_nodes = [cell] + [
                indexed[index]
                for index in descendants(cell_index)
                if index in indexed
            ]
            business_labels = [
                item for item in cell_nodes if is_business_content_label(item)
            ]
            media_nodes = [
                item
                for item in cell_nodes
                if item.get("type") == "Image"
                or looks_like_media_region(item.get("label"))
                or looks_like_media_region(item.get("identifier"))
            ]
            if business_labels:
                business_cells.append(cell)
                business_label_count += len(business_labels)
            if media_nodes:
                media_cells.append(cell)
                media_descendant_count += len(media_nodes)
        business_cell_centers = [
            rect(item)["y"] + rect(item)["height"] / 2.0
            for item in business_cells
            if rect(item)["height"] > 0
        ]
        vertical_business_span = (
            max(business_cell_centers) - min(business_cell_centers)
            if len(business_cell_centers) >= 2
            else 0.0
        )
        vertical_business_evidence = bool(
            len(business_cells) >= 2
            and business_label_count >= 2
            and vertical_business_span >= value["height"] * 0.12
        )
        horizontal_evidence = [
            item
            for item in candidate_descendants
            if is_horizontal_scrollbar(item)
            and rect(item)["width"] >= value["width"] * 0.45
        ]
        nested_scroll_container_count = sum(
            1
            for item in candidate_descendants
            if item.get("type") in {"ScrollView", "Table", "CollectionView"}
        )
        score = width_ratio * 2.0 + height_ratio * 2.0
        if node_type == "ScrollView":
            score += 4.0
        elif node_type == "Table":
            score += 3.5
        else:
            score += 3.0
        if height_ratio >= 0.75:
            score += 2.0
        if node.get("hiddenContentBelow"):
            score += 2.0
        media_hint = bool(
            looks_like_media_region(node.get("label"))
            or looks_like_media_region(identifier)
        )
        media_cell_ratio = (
            len(media_cells) / len(direct_cells) if direct_cells else 0.0
        )
        if not media_hint:
            container_role = "non_media"
        elif vertical_business_evidence and media_cell_ratio < 0.75:
            container_role = "media_led_detail"
        elif not business_cells and (
            media_descendant_count > 0 or horizontal_evidence
        ):
            container_role = "media_only"
        else:
            container_role = "ambiguous_media_container"
        if vertical_evidence:
            score += 3.0
        if vertical_cell_evidence:
            score += 3.0
        if identifier_hint:
            score += 1.5
        if container_role == "media_led_detail":
            score += 1.0
        elif container_role == "ambiguous_media_container":
            score -= 2.0
        elif container_role == "media_only":
            score -= 8.0
        diagnostics = {
            "index": candidate_index,
            "ref": node.get("ref"),
            "type": node_type,
            "label": node.get("label"),
            "identifier": node.get("identifier"),
            "rect": value,
            "score": round(score, 3),
            "has_vertical_scrollbar_evidence": bool(vertical_evidence),
            "has_vertical_cell_evidence": vertical_cell_evidence,
            "direct_cell_count": len(direct_cells),
            "vertical_cell_span": round(vertical_cell_span, 3),
            "media_hint": media_hint,
            "container_role": container_role,
            "business_content_cell_count": len(business_cells),
            "business_content_label_count": business_label_count,
            "vertical_business_content_span": round(vertical_business_span, 3),
            "has_vertical_business_content_evidence": vertical_business_evidence,
            "media_cell_count": len(media_cells),
            "media_cell_ratio": round(media_cell_ratio, 3),
            "media_descendant_count": media_descendant_count,
            "has_horizontal_scrollbar_evidence": bool(horizontal_evidence),
            "nested_scroll_container_count": nested_scroll_container_count,
        }
        if node_type == "CollectionView" and not collection_has_vertical_structure:
            diagnostics["eligible"] = False
            diagnostics["rejection_reason"] = "insufficient_vertical_page_structure"
            all_candidate_diagnostics.append(diagnostics)
            continue
        if container_role == "media_only":
            diagnostics["eligible"] = False
            diagnostics["rejection_reason"] = "media_only_collection_is_not_page_container"
            all_candidate_diagnostics.append(diagnostics)
            continue
        diagnostics["eligible"] = True
        diagnostics["rejection_reason"] = None
        all_candidate_diagnostics.append(diagnostics)
        scroll_candidates.append((score, node, diagnostics))
    if not scroll_candidates:
        if any(
            item.get("rejection_reason") == "media_only_collection_is_not_page_container"
            for item in all_candidate_diagnostics
        ):
            raise PipelineError(
                "Only media-only scroll containers were found; preserve the viewport instead of treating a gallery as the page"
            )
        raise SemanticFallbackRequired(
            "no_main_scroll_container",
            "Unable to identify a main vertical scroll container",
        )
    selected_candidate = max(scroll_candidates, key=lambda item: item[0])
    scroll = selected_candidate[1]
    selected_index = int(scroll.get("index", 0))
    candidate_diagnostics = [
        {**item, "selected": bool(item.get("eligible") and item.get("index") == selected_index)}
        for item in sorted(
            all_candidate_diagnostics,
            key=lambda candidate: candidate["score"],
            reverse=True,
        )
    ]
    selected_container_role = str(selected_candidate[2]["container_role"])
    container_role_warning = (
        "main_container_media_identity_ambiguous"
        if selected_container_role == "ambiguous_media_container"
        else None
    )
    scroll_index = int(scroll.get("index", 0))
    scroll_rect = rect(scroll)
    descendant_indexes = descendants(scroll_index)
    ancestor_indexes = ancestors(scroll_index)
    descendant_nodes = [indexed[index] for index in descendant_indexes if index in indexed]
    selected_direct_cells = [
        indexed[index]
        for index in children.get(scroll_index, [])
        if index in indexed and indexed[index].get("type") == "Cell"
    ]

    descendant_extent = max(
        [scroll_rect["height"]]
        + [node_bottom(node) - scroll_rect["y"] for node in descendant_nodes]
    )
    result_count_candidates = [
        count
        for count in (
            semantic_result_count(value)
            for value in (
                scroll.get("label"),
                scroll.get("identifier"),
                *(node.get("label") for node in descendant_nodes),
            )
        )
        if count is not None
    ]
    semantic_results_total = max(result_count_candidates) if result_count_candidates else None
    large_result_set = bool(
        semantic_results_total is not None and semantic_results_total >= 100
    )
    scrollbar_estimate: float | None = None
    scroll_position_percent: float | None = None
    scrollbar_candidates: list[dict[str, Any]] = []
    for node in descendant_nodes:
        value = rect(node)
        if not is_vertical_scrollbar(node):
            continue
        if value["height"] < scroll_rect["height"] * 0.60:
            continue
        if value["width"] > root_rect["width"] * 0.20:
            continue
        scrollbar_candidates.append(node)
    if scrollbar_candidates:
        scrollbar = max(scrollbar_candidates, key=lambda item: rect(item)["height"])
        scroll_position_percent = percentage(scrollbar.get("value"))
        track = rect(scrollbar)
        direct_children = [
            indexed[index] for index in children.get(int(scrollbar.get("index", 0)), []) if index in indexed
        ]
        thumbs = [
            node
            for node in direct_children
            if 0 < rect(node)["height"] < track["height"] * 0.95
            and rect(node)["width"] <= max(8.0, track["width"])
        ]
        if thumbs:
            thumb = max(thumbs, key=lambda item: rect(item)["height"])
            fraction = rect(thumb)["height"] / track["height"]
            if 0.05 <= fraction < 0.98:
                scrollbar_estimate = scroll_rect["height"] / fraction
    page_counts = [
        count
        for count in (semantic_page_count(node.get("label")) for node in scrollbar_candidates)
        if count is not None
    ]
    scrollbar_page_count = max(page_counts) if page_counts else None
    if scroll_position_percent is not None and scroll_position_percent > 3.0:
        raise PipelineError(
            f"Main scroll container is not at the top: {scroll_position_percent:.1f}%"
        )

    estimates = [descendant_extent]
    height_sources = ["descendant_extent"]
    if scrollbar_estimate is not None:
        estimates.append(scrollbar_estimate)
        height_sources.append("scrollbar_thumb_ratio")
    page_count_fallback_used = bool(
        scrollbar_estimate is None
        and scrollbar_page_count is not None
        and scrollbar_page_count >= 2.0
        and descendant_extent <= scroll_rect["height"] * 1.5
    )
    if page_count_fallback_used:
        estimates.append(scroll_rect["height"] * float(scrollbar_page_count))
        height_sources.append("scrollbar_page_count")
    content_height = max(scroll_rect["height"], max(estimates))
    virtualized_loaded_window = bool(
        scrollbar_estimate is not None
        and scroll.get("type") in {"Table", "CollectionView"}
        and scroll.get("hiddenContentBelow")
        and 1 <= len(selected_direct_cells) <= 12
        and descendant_extent <= scroll_rect["height"] * 1.5
    )
    if large_result_set:
        height_warning = "large_result_count_not_treated_as_bounded"
    elif virtualized_loaded_window:
        height_warning = "virtualized_container_height_not_treated_as_bounded"
    elif page_count_fallback_used:
        height_warning = "content_height_uses_accessibility_page_count_fallback"
    else:
        height_warning = None
    if (
        height_warning is None
        and len(estimates) > 1
        and min(estimates) > 0
        and max(estimates) / min(estimates) > 1.35
    ):
        height_warning = "semantic_height_estimates_diverge"
    bounded_height = bool(
        selected_container_role != "ambiguous_media_container"
        and
        not virtualized_loaded_window
        and not large_result_set
        and (
            scrollbar_estimate is not None
            or descendant_extent > scroll_rect["height"] * 1.5
        )
    )
    height_confidence = "bounded" if bounded_height else "unknown"
    capture_strategy = "recording" if bounded_height else "adaptive_still"
    if selected_container_role == "ambiguous_media_container":
        strategy_reason = "ambiguous_media_identity_prefers_viewport_evidence"
    elif bounded_height:
        strategy_reason = "bounded_semantic_content_height"
    elif large_result_set:
        strategy_reason = "large_result_set_is_virtualized_or_unbounded"
    elif virtualized_loaded_window:
        strategy_reason = "virtualized_loaded_cell_window_is_not_a_bounded_height"
    elif page_count_fallback_used:
        strategy_reason = "accessibility_page_count_only_is_not_a_bounded_height"
    else:
        strategy_reason = "virtualized_or_unbounded_semantic_content_height"

    scale_x = pixel_width / root_rect["width"]
    scale_y = pixel_height / root_rect["height"]
    outside_indexes = set(indexed) - descendant_indexes - ancestor_indexes - {scroll_index, root_index}
    outside_nodes = [indexed[index] for index in outside_indexes]
    top_fixed = [
        node
        for node in outside_nodes
        if rect(node)["width"] >= root_rect["width"] * 0.70
        and rect(node)["height"] >= 5
        and rect(node)["height"] <= root_rect["height"] * 0.20
        and rect(node)["y"] <= root_rect["height"] * 0.15
        and node_bottom(node) <= root_rect["height"] * 0.25
    ]
    bottom_fixed = [
        node
        for node in outside_nodes
        if rect(node)["width"] >= root_rect["width"] * 0.70
        and rect(node)["height"] >= 5
        and rect(node)["height"] <= root_rect["height"] * 0.30
        and rect(node)["y"] >= root_rect["height"] * 0.70
        and node_bottom(node) <= root_rect["height"] + 5
    ]
    top_points = max(
        60.0,
        max([node_bottom(node) - scroll_rect["y"] for node in top_fixed] or [0.0]),
    )
    bottom_edge = min([rect(node)["y"] for node in bottom_fixed] or [scroll_rect["y"] + scroll_rect["height"]])
    bottom_points = max(
        35.0,
        root_rect["height"] - (scroll_rect["y"] + scroll_rect["height"]),
        root_rect["height"] - bottom_edge,
    )
    top_crop = (
        top_crop_override
        if top_crop_override is not None
        else min(round(top_points * scale_y), round(pixel_height * 0.22))
    )
    bottom_crop = (
        bottom_crop_override
        if bottom_crop_override is not None
        else min(round(bottom_points * scale_y), round(pixel_height * 0.30))
    )
    x_margin = (
        x_margin_override
        if x_margin_override is not None
        else max(0, round(pixel_width * 0.025))
    )
    if min(top_crop, bottom_crop, x_margin) < 0 or top_crop + bottom_crop >= pixel_height:
        raise PipelineError("Automatically derived crop geometry is invalid")

    dynamic_media_regions: list[dict[str, Any]] = []
    for node in descendant_nodes:
        value = rect(node)
        if node.get("type") not in {"ScrollView", "Collection", "CollectionView"}:
            continue
        if value["width"] < root_rect["width"] * 0.80:
            continue
        if not root_rect["height"] * 0.20 <= value["height"] <= root_rect["height"] * 0.70:
            continue
        if value["y"] > root_rect["y"] + root_rect["height"] * 0.15:
            continue
        context = " ".join(
            str(part or "")
            for part in (node.get("label"), node.get("identifier"))
        )
        if not looks_like_media_region(context):
            continue
        dynamic_media_regions.append(
            {
                "index": int(node.get("index", 0)),
                "type": node.get("type"),
                "label": node.get("label"),
                "identifier": node.get("identifier"),
                "rect": value,
            }
        )
    continuity_top_crop = int(top_crop)
    if dynamic_media_regions:
        dynamic_bottom_points = max(
            region["rect"]["y"] + region["rect"]["height"] - root_rect["y"]
            for region in dynamic_media_regions
        )
        desired_crop = round(dynamic_bottom_points * scale_y)
        minimum_comparison_height = max(480, round(pixel_height * 0.20))
        maximum_crop = pixel_height - int(bottom_crop) - minimum_comparison_height
        if maximum_crop > continuity_top_crop:
            continuity_top_crop = max(
                continuity_top_crop,
                min(desired_crop, maximum_crop),
            )

    default_scroll_ratio = 0.55 if capture_strategy == "recording" else 0.50
    default_scroll_ceiling = 500.0 if capture_strategy == "recording" else 450.0
    scroll_distance = (
        scroll_distance_override
        if scroll_distance_override is not None
        else max(
            200.0,
            min(
                default_scroll_ceiling,
                round(scroll_rect["height"] * default_scroll_ratio / 10.0) * 10.0,
            ),
        )
    )
    if scroll_distance <= 0:
        raise PipelineError("Scroll distance must be positive")
    gesture_x = (
        gesture_x_override
        if gesture_x_override is not None
        else centered_gesture_x(root_rect, scroll_rect)
    )
    gesture_y = (
        gesture_y_override
        if gesture_y_override is not None
        else round(
            max(
                scroll_rect["y"] + 200.0,
                min(
                    scroll_rect["y"] + scroll_rect["height"] - 100.0,
                    root_rect["height"] * 0.77,
                ),
            )
        )
    )
    if not (
        root_rect["x"] <= gesture_x <= root_rect["x"] + root_rect["width"]
        and root_rect["y"] <= gesture_y <= root_rect["y"] + root_rect["height"]
    ):
        raise PipelineError("Gesture start point is outside the app viewport")
    return {
        "root_rect": root_rect,
        "scroll_node": {
            "index": scroll_index,
            "ref": scroll.get("ref"),
            "type": scroll.get("type"),
            "label": scroll.get("label"),
            "identifier": scroll.get("identifier"),
            "rect": scroll_rect,
            "container_role": selected_container_role,
        },
        "scroll_candidates": candidate_diagnostics,
        "container_role": selected_container_role,
        "container_role_warning": container_role_warning,
        "visible_height": scroll_rect["height"],
        "content_height": content_height,
        "height_estimates": {
            source: round(value, 3) for source, value in zip(height_sources, estimates)
        },
        "height_warning": height_warning,
        "height_confidence": height_confidence,
        "capture_strategy": capture_strategy,
        "capture_strategy_reason": strategy_reason,
        "scrollbar_page_count": scrollbar_page_count,
        "semantic_results_total": semantic_results_total,
        "scroll_position_percent": scroll_position_percent,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "scroll_distance": scroll_distance,
        "required_progress_px": max(0.0, content_height - scroll_rect["height"]) * scale_y,
        "visible_height_px": scroll_rect["height"] * scale_y,
        "crops": {
            "top_crop": int(top_crop),
            "bottom_crop": int(bottom_crop),
            "x_margin": int(x_margin),
        },
        "continuity_crops": {
            "top_crop": int(continuity_top_crop),
            "bottom_crop": int(bottom_crop),
            "x_margin": int(x_margin),
        },
        "dynamic_media_regions": dynamic_media_regions,
        "gesture": {
            "x": int(gesture_x),
            "y": int(gesture_y),
            "dx": 0,
            "dy": -round(scroll_distance),
        },
    }


def build_visual_coordinate_plan(
    pixel_width: int,
    pixel_height: int,
    scroll_distance_override: float | None,
    top_crop_override: int | None,
    bottom_crop_override: int | None,
    x_margin_override: int | None,
    gesture_x_override: int | None,
    gesture_y_override: int | None,
) -> dict[str, Any]:
    """Build a conservative, page-agnostic plan when semantics are unusable."""
    if pixel_width <= 0 or pixel_height <= 0:
        raise PipelineError(
            "Screenshot dimensions must be positive for coordinate fallback",
            EXIT_ERROR,
        )

    if CONFIGURED_VIEWPORT_WIDTH is None or CONFIGURED_VIEWPORT_HEIGHT is None:
        raise PipelineError(
            "Coordinate fallback is disabled because CSI_VIEWPORT_WIDTH and "
            "CSI_VIEWPORT_HEIGHT are not configured; preserve viewport evidence instead"
        )

    reference_aspect = CONFIGURED_VIEWPORT_WIDTH / CONFIGURED_VIEWPORT_HEIGHT
    screenshot_aspect = pixel_width / pixel_height
    aspect_error = abs(screenshot_aspect - reference_aspect) / reference_aspect
    if aspect_error > 0.05:
        raise PipelineError(
            "Screenshot aspect ratio does not match the configured coordinate "
            "viewport; refusing semantic fallback"
        )

    root_rect = {
        "x": 0.0,
        "y": 0.0,
        "width": CONFIGURED_VIEWPORT_WIDTH,
        "height": CONFIGURED_VIEWPORT_HEIGHT,
    }
    scale_x = pixel_width / CONFIGURED_VIEWPORT_WIDTH
    scale_y = pixel_height / CONFIGURED_VIEWPORT_HEIGHT
    top_crop = (
        top_crop_override
        if top_crop_override is not None
        else round(pixel_height * 0.22)
    )
    bottom_crop = (
        bottom_crop_override
        if bottom_crop_override is not None
        else round(pixel_height * 0.15)
    )
    x_margin = (
        x_margin_override
        if x_margin_override is not None
        else max(0, round(pixel_width * 0.025))
    )
    if min(top_crop, bottom_crop, x_margin) < 0 or top_crop + bottom_crop >= pixel_height:
        raise PipelineError("Coordinate fallback crop geometry is invalid")

    scroll_distance = (
        scroll_distance_override
        if scroll_distance_override is not None
        else max(
            200.0,
            min(
                450.0,
                round(CONFIGURED_VIEWPORT_HEIGHT * 0.46 / 10.0) * 10.0,
            ),
        )
    )
    if scroll_distance <= 0:
        raise PipelineError("Scroll distance must be positive")
    gesture_x = (
        gesture_x_override
        if gesture_x_override is not None
        else round(CONFIGURED_VIEWPORT_WIDTH * 0.50)
    )
    gesture_y = (
        gesture_y_override
        if gesture_y_override is not None
        else round(CONFIGURED_VIEWPORT_HEIGHT * 0.77)
    )
    end_y = gesture_y - scroll_distance
    if not (
        0 <= gesture_x <= CONFIGURED_VIEWPORT_WIDTH
        and 0 <= gesture_y <= CONFIGURED_VIEWPORT_HEIGHT
        and 0 <= end_y <= CONFIGURED_VIEWPORT_HEIGHT
    ):
        raise PipelineError(
            "Coordinate fallback gesture starts or ends outside the configured viewport"
        )

    crops = {
        "top_crop": int(top_crop),
        "bottom_crop": int(bottom_crop),
        "x_margin": int(x_margin),
    }
    return {
        "geometry_source": "visual_coordinate_fallback",
        "root_rect": root_rect,
        "scroll_node": {
            "index": None,
            "ref": None,
            "type": "VisualCoordinateRegion",
            "label": None,
            "identifier": None,
            "rect": root_rect,
        },
        "scroll_candidates": [],
        "visible_height": CONFIGURED_VIEWPORT_HEIGHT,
        "content_height": CONFIGURED_VIEWPORT_HEIGHT,
        "height_estimates": {},
        "height_warning": "semantic_snapshot_unavailable_coordinate_fallback",
        "height_confidence": "unknown",
        "capture_strategy": "adaptive_still",
        "capture_strategy_reason": "semantic_snapshot_unavailable",
        "scrollbar_page_count": None,
        "scroll_position_percent": None,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "scroll_distance": scroll_distance,
        "required_progress_px": 0.0,
        "visible_height_px": float(pixel_height),
        "crops": crops,
        "continuity_crops": dict(crops),
        "dynamic_media_regions": [],
        "gesture": {
            "x": int(gesture_x),
            "y": int(gesture_y),
            "dx": 0,
            "dy": -round(scroll_distance),
        },
    }


class Pipeline:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.script_dir = Path(__file__).resolve().parent
        raw_output = Path(args.output).expanduser()
        self.output_was_absolute = raw_output.is_absolute()
        self.output = raw_output.resolve()
        self.before = Path(args.before_screenshot).expanduser().resolve()
        self.work_dir = (
            Path(args.work_dir).expanduser().resolve()
            if args.work_dir
            else self.output.parent / f"{self.output.stem}.fast-run"
        )
        self.run_path = self.work_dir / "run.json"
        self.started = time.monotonic()
        self.reporting_ready = False
        self.skill_root = self.script_dir.parent
        started_at = utc_now()
        run_id = args.run_id or f"csi-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
        self.state: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": args.case_id,
            "skill_hash": hash_skill_tree(self.skill_root),
            "variant": args.variant or detect_variant(self.skill_root),
            "started_at": started_at,
            "environment": {
                "python": platform.python_version(),
                "opencv": cv2.__version__,
                "platform": platform.platform(),
            },
            "pipeline": "capture_long_fast",
            "status": "running",
            "decision": None,
            "final_task_result": "running",
            "expected_bundle": args.expected_bundle,
            "session": args.session,
            "capture_extent": str(args.capture_extent).strip().lower(),
            "before_screenshot": str(self.before),
            "output": str(self.output),
            "work_dir": str(self.work_dir),
            "current_stage": "initializing",
            "completed_stages": [],
            "stage_timings_ms": {},
            "attempts": [],
            "fallback_chain": [],
            "metrics": {
                "agent_device_commands": 0,
                "snapshots": 0,
                "screenshots": 0,
                "scrolls": 0,
            },
            "failure": None,
            "viewport_evidence_pack": None,
            "warnings": [],
            "semantic_fallback": {"used": False},
        }

    def persist(self) -> None:
        if not self.reporting_ready:
            return
        self.state["elapsed_ms"] = round((time.monotonic() - self.started) * 1000)
        if self.state.get("status") == "complete":
            self.state["final_task_result"] = (
                "pass_with_warnings"
                if self.state.get("decision") == "accept_with_warnings" or self.state.get("warnings")
                else "pass"
            )
        elif self.state.get("status") == "failed":
            self.state["final_task_result"] = "fail"
        atomic_write_json(self.run_path, self.state)

    def stage(self, name: str, function: Callable[[], T]) -> T:
        self.state["current_stage"] = name
        attempt = {
            "attempt_id": f"attempt-{len(self.state['attempts']) + 1:03d}",
            "stage": name,
            "started_at": utc_now(),
            "outcome": "running",
        }
        self.state["attempts"].append(attempt)
        self.persist()
        started = time.monotonic()
        try:
            result = function()
            attempt["outcome"] = "pass"
            if name not in self.state["completed_stages"]:
                self.state["completed_stages"].append(name)
            return result
        except Exception as error:
            attempt["outcome"] = "fail"
            attempt["summary"] = " ".join(str(error).splitlines())[:240]
            raise
        finally:
            attempt["finished_at"] = utc_now()
            self.state["stage_timings_ms"][name] = round((time.monotonic() - started) * 1000)
            self.persist()

    def agent(self, *parts: str) -> list[str]:
        self.state["metrics"]["agent_device_commands"] += 1
        if parts and parts[0] == "snapshot":
            self.state["metrics"]["snapshots"] += 1
        elif parts and parts[0] == "screenshot":
            self.state["metrics"]["screenshots"] += 1
        elif len(parts) >= 2 and parts[0] == "gesture" and parts[1] == "pan":
            self.state["metrics"]["scrolls"] += 1
        return ["agent-device", *parts, "--session", self.args.session, "--json"]

    def command(
        self,
        command: list[str],
        label: str,
        allowed: tuple[int, ...] = (0,),
        log_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        remaining_seconds = self.args.max_runtime_seconds - (
            time.monotonic() - self.started
        )
        if remaining_seconds <= 0:
            raise RuntimeLimitError(
                f"Runtime safety cap reached before starting {label}"
            )
        return run_command(
            command,
            label,
            allowed=allowed,
            log_path=log_path,
            timeout_seconds=remaining_seconds,
        )

    def capture_recording_endpoint(
        self,
        segment_zero: Path,
        geometry: dict[str, Any],
    ) -> Path:
        endpoint = self.work_dir / "recording-endpoint.png"
        self.command(
            self.agent("screenshot", str(endpoint)),
            "recording failure endpoint screenshot",
            log_path=self.work_dir / "logs/recording-endpoint-screenshot.json",
        )
        self.command(
            [str(self.script_dir / "check-viewport.sh"), "--image", str(endpoint)],
            "recording failure endpoint viewport check",
            log_path=self.work_dir / "logs/recording-endpoint-check.json",
        )
        crops = geometry["continuity_crops"]
        self.command(
            [
                str(self.script_dir / "check-target-app.sh"),
                "--expected-bundle",
                self.args.expected_bundle,
                "--before-screenshot",
                str(segment_zero),
                "--after-screenshot",
                str(endpoint),
                "--top-crop",
                str(crops["top_crop"]),
                "--bottom-crop",
                str(crops["bottom_crop"]),
                "--x-margin",
                str(crops["x_margin"]),
                "--continuity-mode",
                "scrolled",
                "--session",
                self.args.session,
            ],
            "recording failure endpoint target check",
            log_path=self.work_dir / "logs/recording-endpoint-target.json",
        )
        self.state["segment_paths"] = [
            str(segment_zero.resolve()),
            str(endpoint.resolve()),
        ]
        return endpoint

    def record_capture_extent_result(
        self,
        output_height_px: int,
        stop_reason: str,
        page_complete: bool,
    ) -> None:
        frame_height = int(self.state["before_dimensions"]["height"])
        captured_viewports = output_height_px / frame_height
        policy = self.state["capture_extent_policy"]
        policy.update(
            {
                "captured_viewports": round(captured_viewports, 3),
                "page_complete": page_complete,
                "stop_reason": stop_reason,
            }
        )
        self.state.update(
            {
                "captured_viewports": round(captured_viewports, 3),
                "page_complete": page_complete,
                "stop_reason": stop_reason,
            }
        )
        self.persist()
        hard_limit = policy.get("hard_limit_viewports")
        if hard_limit is not None and captured_viewports > float(hard_limit):
            raise PipelineError(
                "Final output exceeds the auto hard viewport limit: "
                f"{captured_viewports:.3f} > {float(hard_limit):.3f}"
            )

    def prepare(self) -> None:
        if not self.before.is_file():
            raise PipelineError(f"Before screenshot does not exist: {self.before}", EXIT_ERROR)
        if not self.output_was_absolute or self.output.suffix.lower() != ".png":
            raise PipelineError("--output must be an absolute .png path", EXIT_ERROR)
        if self.output.exists() and not self.args.overwrite:
            raise PipelineError(f"Output already exists: {self.output}", EXIT_ERROR)
        if self.work_dir.exists() and any(self.work_dir.iterdir()):
            raise PipelineError(
                f"Work directory is not empty; choose a fresh --work-dir: {self.work_dir}",
                EXIT_ERROR,
            )
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / "logs").mkdir(exist_ok=True)
        (self.work_dir / "probes").mkdir(exist_ok=True)
        (self.work_dir / "accepted").mkdir(exist_ok=True)
        self.reporting_ready = True
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if shutil.which("agent-device") is None:
            raise PipelineError("agent-device is unavailable on PATH", EXIT_ERROR)
        before_image = cv2.imread(str(self.before), cv2.IMREAD_COLOR)
        if before_image is None:
            raise PipelineError(f"Unable to decode before screenshot: {self.before}", EXIT_ERROR)
        self.state["before_dimensions"] = {
            "width": int(before_image.shape[1]),
            "height": int(before_image.shape[0]),
        }
        self.persist()

    def run_adaptive_still(
        self, geometry: dict[str, Any], segment_zero: Path
    ) -> int:
        crops = geometry["crops"]
        gesture = geometry["gesture"]
        accepted_dir = self.work_dir / "accepted"
        probes_dir = self.work_dir / "probes"
        initial = accepted_dir / "segment-000.png"
        shutil.copy2(segment_zero, initial)
        accepted_paths = [str(initial.resolve())]
        iterations: list[dict[str, Any]] = []
        consecutive_no_progress = 0
        cumulative_progress_px = 0.0
        stop_reason: str | None = None
        extent_policy = self.state["capture_extent_policy"]
        target_progress_px = extent_policy.get("target_progress_px")
        hard_progress_px = extent_policy.get("hard_progress_px")
        timing_totals = {
            "gesture_ms": 0,
            "screenshot_ms": 0,
            "validation_ms": 0,
        }
        no_progress_reasons = {
            "duplicate_or_no_progress",
            "no_vertical_progress",
        }

        def timed_command(
            command: list[str],
            label: str,
            allowed: tuple[int, ...] = (0,),
            log_path: Path | None = None,
        ) -> tuple[subprocess.CompletedProcess[str], int]:
            started = time.monotonic()
            result = self.command(command, label, allowed=allowed, log_path=log_path)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            return result, elapsed_ms

        def capture_loop() -> dict[str, Any]:
            nonlocal consecutive_no_progress, cumulative_progress_px, stop_reason
            if target_progress_px is not None and float(target_progress_px) <= 0:
                stop_reason = (
                    extent_policy.get("limit_stop_reason")
                    or "user_approved_limit_reached"
                )
                return {
                    "iterations": iterations,
                    "accepted_count": len(accepted_paths),
                    "accepted_paths": accepted_paths,
                    "stop_reason": stop_reason,
                    "cumulative_progress_px": cumulative_progress_px,
                    "consecutive_no_progress": consecutive_no_progress,
                    "timing_totals_ms": timing_totals,
                }
            for attempt in range(1, self.args.max_still_scrolls + 1):
                elapsed_seconds = time.monotonic() - self.started
                if elapsed_seconds >= self.args.max_runtime_seconds:
                    stop_reason = "runtime_safety_cap"
                    self.state["warnings"].append(
                        "adaptive_still_stopped_at_runtime_safety_cap"
                    )
                    break

                probe = probes_dir / f"probe-{attempt:03}.png"
                end_y = round(float(gesture["y"]) + float(gesture["dy"]))
                _, gesture_ms = timed_command(
                    self.agent(
                        "gesture",
                        "pan",
                        str(gesture["x"]),
                        str(gesture["y"]),
                        "0",
                        str(end_y - float(gesture["y"])),
                        str(self.args.duration_ms),
                    ),
                    f"adaptive still gesture {attempt}",
                    log_path=self.work_dir / "logs" / f"still-gesture-{attempt:03}.json",
                )
                _, screenshot_ms = timed_command(
                    self.agent("screenshot", str(probe)),
                    f"adaptive still screenshot {attempt}",
                    log_path=self.work_dir / "logs" / f"still-screenshot-{attempt:03}.json",
                )
                previous = Path(accepted_paths[-1])
                validation, validation_ms = timed_command(
                    [
                        str(self.script_dir / "validate-probe.sh"),
                        "--mode",
                        "fast",
                        "--previous",
                        str(previous),
                        "--probe",
                        str(probe),
                        "--top-crop",
                        str(crops["top_crop"]),
                        "--bottom-crop",
                        str(crops["bottom_crop"]),
                        "--x-margin",
                        str(crops["x_margin"]),
                    ],
                    f"adaptive still validation {attempt}",
                    allowed=(0, 10, 11),
                    log_path=self.work_dir / "logs" / f"still-validation-{attempt:03}.json",
                )
                payload = parse_json_output(
                    validation.stdout, f"adaptive still validation {attempt}"
                )
                timing_totals["gesture_ms"] += gesture_ms
                timing_totals["screenshot_ms"] += screenshot_ms
                timing_totals["validation_ms"] += validation_ms
                iteration = {
                    "attempt": attempt,
                    "probe": str(probe),
                    "validation_exit_code": validation.returncode,
                    "decision": payload.get("decision"),
                    "reason": payload.get("reason"),
                    "similarity": payload.get("similarity"),
                    "pair": payload.get("pair"),
                    "timings_ms": {
                        "gesture": gesture_ms,
                        "screenshot": screenshot_ms,
                        "validation": validation_ms,
                    },
                }
                if validation.returncode == EXIT_PASS:
                    pair = payload.get("pair") or {}
                    progress_px = float(pair.get("offset_px", 0.0))
                    if progress_px <= 0:
                        raise PipelineError(
                            "Accepted adaptive still probe has no positive progress"
                        )
                    prospective_progress = cumulative_progress_px + progress_px
                    iteration["progress_px"] = round(progress_px, 3)
                    iteration["prospective_progress_px"] = round(
                        prospective_progress, 3
                    )
                    if (
                        hard_progress_px is not None
                        and prospective_progress > float(hard_progress_px)
                    ):
                        iteration["result"] = "excluded_hard_viewport_limit"
                        stop_reason = "hard_viewport_limit_reached"
                    else:
                        destination = accepted_dir / f"segment-{len(accepted_paths):03}.png"
                        shutil.copy2(probe, destination)
                        accepted_paths.append(str(destination.resolve()))
                        cumulative_progress_px = prospective_progress
                        consecutive_no_progress = 0
                        iteration["result"] = "accepted"
                        iteration["segment"] = str(destination)
                        iteration["cumulative_progress_px"] = round(
                            cumulative_progress_px, 3
                        )
                        if (
                            target_progress_px is not None
                            and cumulative_progress_px >= float(target_progress_px)
                        ):
                            stop_reason = (
                                extent_policy.get("limit_stop_reason")
                                or "user_approved_limit_reached"
                            )
                elif (
                    validation.returncode == EXIT_FAIL
                    and payload.get("reason") in no_progress_reasons
                ):
                    consecutive_no_progress += 1
                    iteration["result"] = "excluded_no_progress"
                    iteration["consecutive_no_progress"] = consecutive_no_progress
                    if consecutive_no_progress >= self.args.still_no_progress_count:
                        stop_reason = "successive_visual_no_progress"
                else:
                    iteration["result"] = "unresolved"
                    iterations.append(iteration)
                    self.state["adaptive_still"] = {
                        "iterations": iterations,
                        "accepted_count": len(accepted_paths),
                        "timing_totals_ms": timing_totals,
                    }
                    self.persist()
                    raise PipelineError(
                        "Adaptive still probe could not establish safe vertical progress: "
                        f"{payload.get('reason') or payload}"
                    )
                iterations.append(iteration)
                self.state["adaptive_still"] = {
                    "iterations": iterations,
                    "accepted_count": len(accepted_paths),
                    "consecutive_no_progress": consecutive_no_progress,
                    "cumulative_progress_px": round(cumulative_progress_px, 3),
                    "timing_totals_ms": timing_totals,
                }
                self.persist()
                if stop_reason is not None:
                    break
            else:
                stop_reason = "scroll_count_safety_cap"
                self.state["warnings"].append(
                    "adaptive_still_stopped_at_scroll_count_safety_cap"
                )

            return {
                "iterations": iterations,
                "accepted_count": len(accepted_paths),
                "accepted_paths": accepted_paths,
                "stop_reason": stop_reason,
                "cumulative_progress_px": round(cumulative_progress_px, 3),
                "consecutive_no_progress": consecutive_no_progress,
                "timing_totals_ms": timing_totals,
            }

        report = self.stage("adaptive_still_capture", capture_loop)
        self.state["adaptive_still"] = report
        self.state["segment_paths"] = accepted_paths
        self.persist()

        qa_payload: dict[str, Any]
        if len(accepted_paths) == 1:
            shutil.copy2(initial, self.output)
            qa_payload = {
                "decision": "accept_with_warnings",
                "reasons": ["selected_container_produced_no_visual_progress"],
                "suggested_action": "deliver_the_verified_viewport_as_the_complete_visible_result",
            }
            self.state["warnings"].append(
                "adaptive_still_selected_container_produced_no_visual_progress"
            )
        else:
            def stitch() -> None:
                self.command(
                    [
                        str(self.script_dir / "stitch-long-screenshot.sh"),
                        "--top-crop",
                        str(crops["top_crop"]),
                        "--bottom-crop",
                        str(crops["bottom_crop"]),
                        "--x-margin",
                        str(crops["x_margin"]),
                        "-o",
                        str(self.output),
                        *accepted_paths,
                    ],
                    "adaptive still stitch",
                    log_path=self.work_dir / "logs/adaptive-still-stitch.log",
                )

            def qa() -> tuple[int, dict[str, Any]]:
                result = self.command(
                    [
                        str(self.script_dir / "qa-stitched-output.sh"),
                        "--mode",
                        "fast",
                        "--stitched",
                        str(self.output),
                        "--report",
                        str(self.output.with_suffix(self.output.suffix + ".stitch.json")),
                    ],
                    "adaptive still QA",
                    allowed=(0, 10, 11),
                    log_path=self.work_dir / "qa-adaptive-still.json",
                )
                return result.returncode, parse_json_output(
                    result.stdout, "adaptive still QA"
                )

            self.stage("adaptive_still_stitch", stitch)
            qa_status, qa_payload = self.stage("adaptive_still_qa", qa)
            if qa_status != EXIT_PASS:
                raise PipelineError(
                    "Adaptive still output failed fast QA: "
                    f"{qa_payload.get('reasons') or qa_payload}"
                )

        final_image = cv2.imread(str(self.output), cv2.IMREAD_COLOR)
        if final_image is None:
            raise PipelineError("Unable to decode adaptive still output")
        final_stop_reason = stop_reason or "adaptive_capture_completed"
        page_complete = final_stop_reason == "successive_visual_no_progress"
        self.record_capture_extent_result(
            int(final_image.shape[0]),
            final_stop_reason,
            page_complete,
        )
        decision = qa_payload.get("decision", "accept")
        if self.state["warnings"] and decision == "accept":
            decision = "accept_with_warnings"
        self.state.update(
            {
                "status": "complete",
                "decision": decision,
                "current_stage": "complete",
                "qa": qa_payload,
                "output_dimensions": {
                    "width": int(final_image.shape[1]),
                    "height": int(final_image.shape[0]),
                },
                "segment_paths": accepted_paths,
            }
        )
        self.persist()
        print(json.dumps({"exit_code": 0, **self.state}, ensure_ascii=False, indent=2))
        return EXIT_PASS

    def run(self) -> int:
        self.prepare()

        def target_assertion() -> dict[str, Any]:
            result = self.command(
                self.agent("appstate"),
                "appstate",
                log_path=self.work_dir / "logs/appstate-before.json",
            )
            payload = parse_json_output(result.stdout, "appstate")
            data = payload.get("data") or {}
            reported = data.get("appBundleId") or data.get("appName")
            if reported != self.args.expected_bundle:
                raise PipelineError(
                    f"Target bundle changed before pipeline: expected {self.args.expected_bundle}, got {reported}"
                )
            return data

        self.state["appstate_before"] = self.stage("target_assertion", target_assertion)

        def snapshot_and_plan() -> tuple[dict[str, Any], dict[str, Any]]:
            try:
                result = self.command(
                    self.agent("snapshot", "--level", "default"),
                    "snapshot",
                    log_path=self.work_dir / "logs/snapshot-output.json",
                )
                snapshot = parse_json_output(result.stdout, "snapshot")
            except RuntimeLimitError:
                raise
            except SemanticFallbackRequired:
                raise
            except PipelineError as error:
                if is_semantic_snapshot_timeout(error):
                    raise SemanticFallbackRequired(
                        "snapshot_timeout",
                        f"Semantic snapshot timed out: {error}",
                    ) from error
                raise
            atomic_write_json(self.work_dir / "snapshot.json", snapshot)
            before_dimensions = self.state["before_dimensions"]
            geometry = derive_scroll_plan(
                snapshot,
                before_dimensions["width"],
                before_dimensions["height"],
                self.args.scroll_distance,
                self.args.top_crop,
                self.args.bottom_crop,
                self.args.x_margin,
                self.args.gesture_x,
                self.args.gesture_y,
            )
            return snapshot, geometry

        try:
            _, geometry = self.stage("snapshot_and_plan", snapshot_and_plan)
        except SemanticFallbackRequired as error:
            before_dimensions = self.state["before_dimensions"]
            self.state["semantic_fallback"] = {
                "used": True,
                "trigger": error.trigger,
                "reason": str(error),
                "mode": "visual_coordinate_adaptive_still",
                "configured_viewport": {
                    "width": CONFIGURED_VIEWPORT_WIDTH,
                    "height": CONFIGURED_VIEWPORT_HEIGHT,
                },
            }
            self.state["warnings"].append(
                f"semantic_snapshot_fallback_to_coordinate_still:{error.trigger}"
            )
            self.state["fallback_chain"].append(
                {
                    "fallback_id": f"fallback-{len(self.state['fallback_chain']) + 1:03d}",
                    "from_stage": "snapshot_and_plan",
                    "to_strategy": "visual_coordinate_adaptive_still",
                    "changed_condition": error.trigger,
                    "expected_signal": "validated visual vertical progress",
                }
            )
            self.persist()
            geometry = self.stage(
                "coordinate_fallback_plan",
                lambda: build_visual_coordinate_plan(
                    before_dimensions["width"],
                    before_dimensions["height"],
                    self.args.scroll_distance,
                    self.args.top_crop,
                    self.args.bottom_crop,
                    self.args.x_margin,
                    self.args.gesture_x,
                    self.args.gesture_y,
                ),
            )
        extent_policy = build_capture_extent_policy(
            self.args.capture_extent,
            geometry,
            int(self.state["before_dimensions"]["height"]),
        )
        capture_required_progress = extent_policy.get(
            "capture_required_progress_px"
        )
        if capture_required_progress is None:
            capture_required_progress = geometry["required_progress_px"]
        geometry["capture_required_progress_px"] = float(capture_required_progress)
        geometry["capture_content_height"] = (
            geometry["visible_height"]
            + float(capture_required_progress) / geometry["scale_y"]
        )
        self.state["geometry"] = geometry
        self.state["capture_strategy"] = geometry["capture_strategy"]
        self.state["capture_extent_policy"] = extent_policy
        if geometry.get("height_warning"):
            self.state["warnings"].append(geometry["height_warning"])
        if geometry.get("container_role_warning"):
            self.state["warnings"].append(geometry["container_role_warning"])
        self.persist()

        segment_zero = self.work_dir / "segment-000.png"

        def continuity_capture() -> None:
            self.command(
                self.agent("screenshot", str(segment_zero)),
                "post-snapshot screenshot",
                log_path=self.work_dir / "logs/segment-zero.json",
            )
            self.command(
                [str(self.script_dir / "check-viewport.sh"), "--image", str(segment_zero)],
                "viewport check",
                log_path=self.work_dir / "logs/segment-zero-check.json",
            )
            crops = geometry["continuity_crops"]
            self.command(
                [
                    str(self.script_dir / "check-target-app.sh"),
                    "--expected-bundle",
                    self.args.expected_bundle,
                    "--before-screenshot",
                    str(self.before),
                    "--after-screenshot",
                    str(segment_zero),
                    "--top-crop",
                    str(crops["top_crop"]),
                    "--bottom-crop",
                    str(crops["bottom_crop"]),
                    "--x-margin",
                    str(crops["x_margin"]),
                    "--session",
                    self.args.session,
                ],
                "target continuity check",
                log_path=self.work_dir / "logs/target-continuity.json",
            )

        self.stage("continuity_capture", continuity_capture)
        self.state["target_verified"] = True
        self.persist()

        if geometry["capture_strategy"] == "adaptive_still":
            return self.run_adaptive_still(geometry, segment_zero)

        def plan_scrolls() -> dict[str, Any]:
            result = self.command(
                [
                    str(self.script_dir / "plan-scroll-count.sh"),
                    "--content-height",
                    str(geometry["capture_content_height"]),
                    "--visible-height",
                    str(geometry["visible_height"]),
                    "--scroll-distance",
                    str(geometry["scroll_distance"]),
                    "--safety-gestures",
                    str(self.args.safety_gestures),
                ],
                "scroll planner",
                log_path=self.work_dir / "scroll-plan.json",
            )
            return parse_json_output(result.stdout, "scroll planner")

        scroll_plan = self.stage("scroll_plan", plan_scrolls)
        self.state["scroll_plan"] = scroll_plan
        self.persist()
        base_count = int(scroll_plan["base_scroll_count"])
        total_count = int(scroll_plan["scroll_count"])
        if total_count == 0:
            shutil.copy2(segment_zero, self.output)
            extent_policy = self.state["capture_extent_policy"]
            page_complete = bool(extent_policy.get("page_complete_expected"))
            stop_reason = (
                "page_bottom_reached"
                if page_complete
                else extent_policy.get("limit_stop_reason")
                or "capture_extent_reached"
            )
            self.record_capture_extent_result(
                int(self.state["before_dimensions"]["height"]),
                stop_reason,
                page_complete,
            )
            self.state.update(
                {
                    "status": "complete",
                    "decision": "accept",
                    "current_stage": "complete",
                    "output_dimensions": self.state["before_dimensions"],
                    "reason": "content_fits_in_one_viewport",
                }
            )
            self.persist()
            print(json.dumps({"exit_code": 0, **self.state}, ensure_ascii=False, indent=2))
            return EXIT_PASS

        video = self.work_dir / "scroll.mp4"

        def record_scrolls() -> None:
            gesture = geometry["gesture"]
            self.command(
                [
                    str(self.script_dir / "record-scroll-batch.sh"),
                    "--output",
                    str(video),
                    "--count",
                    str(total_count),
                    "--session",
                    self.args.session,
                    "--x",
                    str(gesture["x"]),
                    "--y",
                    str(gesture["y"]),
                    "--dx",
                    str(gesture["dx"]),
                    "--dy",
                    str(gesture["dy"]),
                    "--duration-ms",
                    str(self.args.duration_ms),
                    "--pause-seconds",
                    str(self.args.pause_seconds),
                ],
                "bounded recording batch",
                log_path=self.work_dir / "logs/recording.log",
            )

        try:
            self.stage("recording", record_scrolls)
        except PipelineError as recording_error:
            if not is_recording_transport_failure(recording_error):
                raise
            recovery = {
                "attempted": True,
                "trigger": "recording_transport_state_lost",
                "outcome": "running",
                "endpoint": None,
            }
            self.state["recording_recovery"] = recovery
            self.persist()
            try:
                endpoint = self.stage(
                    "recording_endpoint_capture",
                    lambda: self.capture_recording_endpoint(segment_zero, geometry),
                )
                recovery.update(
                    {
                        "outcome": "pass",
                        "endpoint": str(endpoint),
                        "evidence_count": 2,
                    }
                )
                self.state["warnings"].append(
                    "recording_transport_failed_target_verified_endpoint_preserved"
                )
            except PipelineError as recovery_error:
                recovery.update(
                    {
                        "outcome": "fail",
                        "failure": " ".join(str(recovery_error).splitlines())[:240],
                    }
                )
                self.state["warnings"].append(
                    "recording_endpoint_recovery_failed"
                )
            self.state["current_stage"] = "recording"
            self.persist()
            raise recording_error
        self.state["metrics"]["agent_device_commands"] += total_count + 2
        self.state["metrics"]["scrolls"] += total_count
        self.persist()
        telemetry = video.with_suffix(".gesture-telemetry.json")
        if not video.is_file() or not telemetry.is_file():
            raise PipelineError("Recording completed without video or gesture telemetry")

        bottom = self.work_dir / "bottom.png"

        def bottom_capture() -> None:
            self.command(
                self.agent("screenshot", str(bottom)),
                "bottom screenshot",
                log_path=self.work_dir / "logs/bottom-screenshot.json",
            )
            self.command(
                [str(self.script_dir / "check-viewport.sh"), "--image", str(bottom)],
                "bottom viewport check",
                log_path=self.work_dir / "logs/bottom-check.json",
            )

        self.stage("bottom_capture", bottom_capture)

        extraction_report = self.work_dir / "probes/extraction.json"

        def extract_frames() -> None:
            crops = geometry["crops"]
            self.command(
                [
                    str(self.script_dir / "extract-scroll-frames.sh"),
                    "--video",
                    str(video),
                    "--telemetry",
                    str(telemetry),
                    "--output-dir",
                    str(self.work_dir / "probes"),
                    "--top-crop",
                    str(crops["top_crop"]),
                    "--bottom-crop",
                    str(crops["bottom_crop"]),
                    "--x-margin",
                    str(crops["x_margin"]),
                    "--base-gesture-count",
                    str(base_count),
                ],
                "dynamic frame extraction",
                log_path=self.work_dir / "logs/extraction-output.json",
            )

        self.stage("frame_extraction", extract_frames)
        if not extraction_report.is_file():
            raise PipelineError("Frame extractor did not write extraction.json")

        sequence_report = self.work_dir / "accepted/sequence.json"

        def select_sequence() -> None:
            crops = geometry["crops"]
            self.command(
                [
                    str(self.script_dir / "select-scroll-segments.sh"),
                    "--initial",
                    str(segment_zero),
                    "--extraction-report",
                    str(extraction_report),
                    "--bottom-screenshot",
                    str(bottom),
                    "--output-dir",
                    str(self.work_dir / "accepted"),
                    "--base-gesture-count",
                    str(base_count),
                    "--required-progress-px",
                    str(geometry["capture_required_progress_px"]),
                    "--visible-height-px",
                    str(geometry["visible_height_px"]),
                    "--top-crop",
                    str(crops["top_crop"]),
                    "--bottom-crop",
                    str(crops["bottom_crop"]),
                    "--x-margin",
                    str(crops["x_margin"]),
                ],
                "sequence selection",
                log_path=self.work_dir / "logs/sequence-output.json",
            )

        self.stage("sequence_selection", select_sequence)
        sequence = json.loads(sequence_report.read_text(encoding="utf-8"))
        self.state["sequence"] = {
            "coverage_ratio": sequence.get("coverage_ratio"),
            "cumulative_progress_px": sequence.get("cumulative_progress_px"),
            "accepted_count": len(sequence.get("accepted", [])),
            "sequence_confirmed_no_progress": sequence.get(
                "sequence_confirmed_no_progress"
            ),
            "bottom_confirmed_no_progress": sequence.get(
                "bottom_confirmed_no_progress"
            ),
            "visual_terminal_accepted": sequence.get("visual_terminal_accepted"),
            "excluded": sequence.get("excluded", []),
        }
        self.persist()
        segment_paths = [str(Path(path).resolve()) for path in sequence.get("segment_paths", [])]
        self.state["segment_paths"] = segment_paths
        self.persist()
        if len(segment_paths) < 2:
            raise PipelineError("Long-page plan produced fewer than two accepted segments")

        def stitch(paths: list[str], log_suffix: str = "") -> None:
            crops = geometry["crops"]
            self.command(
                [
                    str(self.script_dir / "stitch-long-screenshot.sh"),
                    "--top-crop",
                    str(crops["top_crop"]),
                    "--bottom-crop",
                    str(crops["bottom_crop"]),
                    "--x-margin",
                    str(crops["x_margin"]),
                    "-o",
                    str(self.output),
                    *paths,
                ],
                "long screenshot stitch",
                log_path=self.work_dir / f"logs/stitch{log_suffix}.log",
            )

        def qa(log_suffix: str = "") -> tuple[int, dict[str, Any]]:
            result = self.command(
                [
                    str(self.script_dir / "qa-stitched-output.sh"),
                    "--mode",
                    "fast",
                    "--stitched",
                    str(self.output),
                    "--report",
                    str(self.output.with_suffix(self.output.suffix + ".stitch.json")),
                ],
                "stitched output QA",
                allowed=(0, 10, 11),
                log_path=self.work_dir / f"qa{log_suffix}.json",
            )
            return result.returncode, parse_json_output(result.stdout, "stitched output QA")

        self.stage("stitch", lambda: stitch(segment_paths))
        qa_status, qa_payload = self.stage("qa", qa)
        original_qa_status = qa_status
        original_qa_payload = qa_payload
        retry_attempted = False
        retried = False
        reasons = set(qa_payload.get("reasons") or [])
        repair_reasons = {
            "duplicate_input_segments",
            "gross_stitched_height_inconsistency",
            "stitched_height_inconsistent_with_pair_offsets",
            "large_repeated_regions_detected",
        }
        accepted = sequence.get("accepted", [])
        last = accepted[-1] if accepted else {}
        previous_progress = sum(float(item.get("progress_px", 0.0)) for item in accepted[:-1])
        required = float(geometry["capture_required_progress_px"])
        ratio_without_last = previous_progress / required if required > 0 else 1.0
        can_drop_last = bool(
            last.get("role") == "safety"
            and reasons & repair_reasons
            and ratio_without_last >= 0.80
            and len(segment_paths) > 2
        )

        def move_stitch_artifacts(source_base: Path, destination_base: Path) -> None:
            for suffix in ("", ".stitch.json", ".stitch.log"):
                source = Path(str(source_base) + suffix)
                destination = Path(str(destination_base) + suffix)
                if source.exists():
                    source.replace(destination)

        if can_drop_last:
            retry_attempted = True
            self.state["fallback_chain"].append(
                {
                    "fallback_id": f"fallback-{len(self.state['fallback_chain']) + 1:03d}",
                    "from_stage": "qa",
                    "to_strategy": "drop_safety_segment_and_restitch",
                    "changed_condition": "remove the low-value safety segment implicated by QA",
                    "expected_signal": "fewer hard QA reasons without coverage below 80%",
                }
            )
            self.persist()
            backup = self.work_dir / "pre-safety-drop.png"
            rejected_retry = self.work_dir / "rejected-safety-drop.png"
            move_stitch_artifacts(self.output, backup)
            retry_paths = segment_paths[:-1]
            retry_status = EXIT_ERROR
            retry_payload: dict[str, Any] = {
                "decision": "error",
                "reasons": ["automatic_safety_drop_retry_failed_to_run"],
            }
            try:
                self.stage("stitch_retry", lambda: stitch(retry_paths, "-retry"))
                retry_status, retry_payload = self.stage("qa_retry", lambda: qa("-retry"))
            except PipelineError as error:
                retry_payload = {"decision": "error", "reasons": [str(error)]}
            retry_reasons = set(retry_payload.get("reasons") or [])
            improved = bool(
                retry_status == EXIT_PASS
                and (
                    original_qa_status != EXIT_PASS
                    or len(retry_reasons & repair_reasons) < len(reasons & repair_reasons)
                )
            )
            if improved:
                retried = True
                segment_paths = retry_paths
                qa_status, qa_payload = retry_status, retry_payload
            else:
                move_stitch_artifacts(self.output, rejected_retry)
                move_stitch_artifacts(backup, self.output)
                qa_status, qa_payload = original_qa_status, original_qa_payload
                self.state["warnings"].append("automatic_safety_drop_retry_reverted")

        if qa_status != EXIT_PASS:
            raise PipelineError(
                f"Stitched output failed fast QA: {qa_payload.get('reasons') or qa_payload}"
            )

        final_image = cv2.imread(str(self.output), cv2.IMREAD_COLOR)
        if final_image is None:
            raise PipelineError("Unable to decode final stitched output")
        extent_policy = self.state["capture_extent_policy"]
        page_complete = bool(
            extent_policy.get("page_complete_expected")
            or sequence.get("visual_terminal_accepted")
        )
        stop_reason = (
            "page_bottom_reached"
            if page_complete
            else extent_policy.get("limit_stop_reason")
            or "capture_extent_reached"
        )
        self.record_capture_extent_result(
            int(final_image.shape[0]),
            stop_reason,
            page_complete,
        )
        elapsed_ms = round((time.monotonic() - self.started) * 1000)
        if elapsed_ms > self.args.max_runtime_seconds * 1000:
            self.state["warnings"].append("pipeline_exceeded_fast_runtime_target")
        self.state.update(
            {
                "status": "complete",
                "decision": qa_payload.get("decision", "accept"),
                "current_stage": "complete",
                "qa": qa_payload,
                "automatic_retry_attempted": retry_attempted,
                "automatic_retry_used": retried,
                "output_dimensions": {
                    "width": int(final_image.shape[1]),
                    "height": int(final_image.shape[0]),
                },
                "segment_paths": segment_paths,
            }
        )
        self.persist()
        print(json.dumps({"exit_code": 0, **self.state}, ensure_ascii=False, indent=2))
        return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-bundle", required=True)
    parser.add_argument("--before-screenshot", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--work-dir")
    parser.add_argument("--case-id", default="ad-hoc")
    parser.add_argument("--run-id")
    parser.add_argument("--variant", choices=("baseline", "candidate"))
    parser.add_argument(
        "--capture-extent",
        default="auto",
        help="auto (soft 4 / hard 6 viewports), full, or a positive viewport count",
    )
    parser.add_argument("--session", default=os.environ.get("AGENT_DEVICE_SESSION", "phone-main"))
    parser.add_argument("--scroll-distance", type=float)
    parser.add_argument("--top-crop", type=int)
    parser.add_argument("--bottom-crop", type=int)
    parser.add_argument("--x-margin", type=int)
    parser.add_argument("--gesture-x", type=int)
    parser.add_argument("--gesture-y", type=int)
    parser.add_argument("--duration-ms", type=int, default=800)
    parser.add_argument("--pause-seconds", type=float, default=0.7)
    parser.add_argument("--safety-gestures", type=int, default=1)
    parser.add_argument("--max-runtime-seconds", type=float, default=90.0)
    parser.add_argument("--max-still-scrolls", type=int, default=20)
    parser.add_argument("--still-no-progress-count", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    pipeline: Pipeline | None = None
    try:
        parse_capture_extent(args.capture_extent)
        if (
            args.duration_ms <= 0
            or args.pause_seconds < 0
            or args.safety_gestures < 0
            or args.max_runtime_seconds <= 0
            or args.max_still_scrolls <= 0
            or args.still_no_progress_count <= 0
        ):
            raise PipelineError("Gesture timing and safety counts are invalid", EXIT_ERROR)
        pipeline = Pipeline(args)
        return pipeline.run()
    except PipelineError as error:
        summary = " ".join(str(error).splitlines())[:240]
        payload: dict[str, Any] = {
            "exit_code": error.exit_code,
            "pipeline": "capture_long_fast",
            "status": "failed",
            "decision": "error" if error.exit_code == EXIT_ERROR else "reject",
            "reason": summary,
        }
        if pipeline is not None and pipeline.reporting_ready:
            stage = str(pipeline.state.get("current_stage") or "unknown")
            failure = {
                "code": classify_failure(stage, str(error)),
                "stage": stage,
                "summary": summary,
                "raw_log": str(pipeline.work_dir / "logs"),
            }
            pipeline.state.update(
                {
                    "status": "failed",
                    "decision": payload["decision"],
                    "reason": summary,
                    "failure": failure,
                }
            )
            try:
                pack_path = build_viewport_evidence_pack(pipeline.work_dir, pipeline.state)
            except Exception as pack_error:
                pack_path = None
                pipeline.state["warnings"].append(
                    "viewport_evidence_pack_failed:" + " ".join(str(pack_error).splitlines())[:160]
                )
            if pack_path is not None:
                pipeline.state["viewport_evidence_pack"] = str(pack_path)
                pack = json.loads(pack_path.read_text(encoding="utf-8"))
                viewport_count = len(pack.get("evidence") or [])
                pipeline.state["fallback_chain"].append(
                    evidence_pack_fallback_entry(pipeline.state, stage)
                )
                pipeline.state["resume_plan"] = {
                    "safe": viewport_count >= 2,
                    "earliest_safe_stage": "offline_stitch" if viewport_count >= 2 else "evidence_delivery",
                    "command": (
                        f"{pipeline.script_dir / 'rebuild-from-evidence-pack.sh'} --pack {pack_path} --output /absolute/recovered.png"
                        if viewport_count >= 2
                        else None
                    ),
                }
                payload["viewport_evidence_pack"] = str(pack_path)
            pipeline.persist()
            payload["run_report"] = str(pipeline.run_path)
            payload["current_stage"] = stage
            payload["failure_code"] = failure["code"]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
