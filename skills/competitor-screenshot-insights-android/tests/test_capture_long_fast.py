from __future__ import annotations

import importlib.util
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

import cv2
import numpy as np


# setdefault() is not enough: the config loader exports these as EMPTY strings
# when coordinate fallback is intentionally disabled, and an empty value would
# leave the fallback "unconfigured" for tests that require it. Treat empty as
# unset while still respecting a real configured value.
for _viewport_name, _viewport_value in (
    ("CSI_VIEWPORT_WIDTH", "390"),
    ("CSI_VIEWPORT_HEIGHT", "844"),
):
    if not os.environ.get(_viewport_name):
        os.environ[_viewport_name] = _viewport_value


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "capture_long_fast.py"
)
SPEC = importlib.util.spec_from_file_location("capture_long_fast", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def geometry(required_progress_px: float, confidence: str = "bounded") -> dict:
    return {
        "required_progress_px": required_progress_px,
        "height_confidence": confidence,
    }


class CaptureExtentPolicyTests(unittest.TestCase):
    def test_auto_captures_short_bounded_page_to_bottom(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "auto", geometry(2000), frame_height_px=1000
        )
        self.assertEqual(policy["estimated_page_viewports"], 3.0)
        self.assertEqual(policy["capture_required_progress_px"], 2000)
        self.assertTrue(policy["page_complete_expected"])
        self.assertIsNone(policy["limit_stop_reason"])

    def test_auto_captures_bounded_page_between_soft_and_hard_to_bottom(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "auto", geometry(4000), frame_height_px=1000
        )
        self.assertEqual(policy["estimated_page_viewports"], 5.0)
        self.assertEqual(policy["capture_required_progress_px"], 4000)
        self.assertTrue(policy["page_complete_expected"])

    def test_auto_captures_page_at_hard_boundary_to_bottom(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "auto", geometry(5000), frame_height_px=1000
        )
        self.assertEqual(policy["estimated_page_viewports"], 6.0)
        self.assertEqual(policy["capture_required_progress_px"], 5000)
        self.assertTrue(policy["page_complete_expected"])

    def test_auto_limits_page_just_above_hard_boundary(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "auto", geometry(5001), frame_height_px=1000
        )
        self.assertEqual(policy["capture_required_progress_px"], 3000)
        self.assertFalse(policy["page_complete_expected"])

    def test_auto_limits_bounded_page_longer_than_hard_limit_to_soft_target(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "auto", geometry(8000), frame_height_px=1000
        )
        self.assertEqual(policy["estimated_page_viewports"], 9.0)
        self.assertEqual(policy["target_viewports"], 4.0)
        self.assertEqual(policy["capture_required_progress_px"], 3000)
        self.assertFalse(policy["page_complete_expected"])
        self.assertEqual(
            policy["limit_stop_reason"], "soft_viewport_limit_reached"
        )

    def test_auto_unknown_height_uses_soft_target(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "auto",
            geometry(0, confidence="unknown"),
            frame_height_px=1000,
        )
        self.assertIsNone(policy["estimated_page_viewports"])
        self.assertEqual(policy["capture_required_progress_px"], 3000)
        self.assertIsNone(policy["page_complete_expected"])
        self.assertEqual(policy["hard_progress_px"], 5000)

    def test_explicit_viewport_count_overrides_auto(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "8", geometry(8000), frame_height_px=1000
        )
        self.assertEqual(policy["approved_viewports"], 8.0)
        self.assertEqual(policy["capture_required_progress_px"], 7000)
        self.assertFalse(policy["page_complete_expected"])
        self.assertEqual(
            policy["limit_stop_reason"], "user_approved_limit_reached"
        )

    def test_explicit_viewport_count_still_finishes_a_shorter_page(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "8", geometry(4000), frame_height_px=1000
        )
        self.assertEqual(policy["capture_required_progress_px"], 4000)
        self.assertTrue(policy["page_complete_expected"])
        self.assertIsNone(policy["limit_stop_reason"])

    def test_full_preserves_existing_bounded_page_progress(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "full", geometry(8000), frame_height_px=1000
        )
        self.assertEqual(policy["capture_required_progress_px"], 8000)
        self.assertTrue(policy["page_complete_expected"])
        self.assertIsNone(policy["hard_limit_viewports"])

    def test_full_unknown_height_keeps_adaptive_terminal_detection(self) -> None:
        policy = MODULE.build_capture_extent_policy(
            "full",
            geometry(0, confidence="unknown"),
            frame_height_px=1000,
        )
        self.assertIsNone(policy["target_progress_px"])
        self.assertIsNone(policy["page_complete_expected"])
        self.assertIsNone(policy["hard_progress_px"])

    def test_rejects_invalid_extent(self) -> None:
        with self.assertRaises(MODULE.PipelineError):
            MODULE.parse_capture_extent("0")
        with self.assertRaises(MODULE.PipelineError):
            MODULE.parse_capture_extent("many")

    def test_final_output_enforces_auto_hard_limit(self) -> None:
        pipeline = object.__new__(MODULE.Pipeline)
        pipeline.state = {
            "before_dimensions": {"height": 1000},
            "capture_extent_policy": {"hard_limit_viewports": 6.0},
        }
        pipeline.persist = lambda: None
        pipeline.record_capture_extent_result(6000, "page_bottom_reached", True)
        with self.assertRaises(MODULE.PipelineError):
            pipeline.record_capture_extent_result(
                6001, "hard_viewport_limit_reached", False
            )


class VersionedRunAndEvidencePackTests(unittest.TestCase):
    def test_failure_codes_are_short_and_stage_specific(self) -> None:
        self.assertEqual("RECORDING_FAILED", MODULE.classify_failure("recording", "command failed"))
        self.assertEqual("TARGET_CONTINUITY", MODULE.classify_failure("continuity_capture", "target bundle changed"))
        self.assertEqual("STITCH_QA", MODULE.classify_failure("adaptive_still_qa", "seam failed"))
        self.assertEqual(
            "RUNTIME_LIMIT",
            MODULE.classify_failure(
                "adaptive_still_capture", "Runtime safety cap reached"
            ),
        )

    def test_command_timeout_enforces_wall_clock_cap_and_writes_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "timeout.log"
            started = time.monotonic()
            with self.assertRaises(MODULE.RuntimeLimitError):
                MODULE.run_command(
                    [sys.executable, "-c", "import time; time.sleep(5)"],
                    "slow fixture",
                    log_path=log_path,
                    timeout_seconds=0.05,
                )
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertIn("runtime safety cap", log_path.read_text(encoding="utf-8"))

    def test_recording_stop_disarms_cleanup_before_finalization_attempt(self) -> None:
        script = (
            MODULE_PATH.parent / "record-scroll-batch.sh"
        ).read_text(encoding="utf-8")
        finalization = script.rsplit("done\n\n", 1)[1]
        self.assertIn(
            'if agent-device record stop --session "$SESSION" --json; then\n'
            '  RECORDING=0\nelse\n  RECORDING=0\n  exit 1\nfi',
            finalization,
        )

    def test_recording_transport_failure_signatures_are_targeted(self) -> None:
        self.assertTrue(
            MODULE.is_recording_transport_failure(
                MODULE.PipelineError("failed to stop recording: video was not finalized into a playable video")
            )
        )
        self.assertTrue(
            MODULE.is_recording_transport_failure(
                MODULE.PipelineError("no active recording")
            )
        )
        self.assertFalse(
            MODULE.is_recording_transport_failure(
                MODULE.PipelineError("gesture pan failed")
            )
        )

    def test_recording_endpoint_capture_builds_two_viewport_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.png"
            initial = root / "work" / "segment-000.png"
            initial.parent.mkdir()
            cv2.imwrite(str(before), np.full((180, 100, 3), 160, dtype=np.uint8))
            cv2.imwrite(str(initial), np.full((180, 100, 3), 170, dtype=np.uint8))
            args = argparse.Namespace(
                output=str(root / "output.png"),
                before_screenshot=str(before),
                work_dir=str(root / "work"),
                run_id="run-endpoint-test",
                case_id="CSI-CASE-005",
                variant="candidate",
                expected_bundle="example.bundle",
                session="phone-main",
                capture_extent="auto",
                max_runtime_seconds=90.0,
            )
            pipeline = MODULE.Pipeline(args)
            pipeline.state["target_verified"] = True
            pipeline.state["current_stage"] = "recording"
            commands: list[list[str]] = []

            def fake_command(command, label, allowed=(0,), log_path=None):
                commands.append(command)
                if len(command) >= 3 and command[0] == "agent-device" and command[1] == "screenshot":
                    endpoint_image = np.full((180, 100, 3), 200, dtype=np.uint8)
                    endpoint_image[60:120, 20:80] = 90
                    cv2.imwrite(command[2], endpoint_image)
                return MODULE.subprocess.CompletedProcess(command, 0, "{}", None)

            pipeline.command = fake_command
            endpoint = pipeline.capture_recording_endpoint(
                initial,
                {
                    "continuity_crops": {
                        "top_crop": 35,
                        "bottom_crop": 20,
                        "x_margin": 4,
                    }
                },
            )
            self.assertTrue(endpoint.is_file())
            self.assertTrue(
                any(
                    "--continuity-mode" in command
                    and command[command.index("--continuity-mode") + 1] == "scrolled"
                    for command in commands
                )
            )
            pack_path = MODULE.build_viewport_evidence_pack(
                pipeline.work_dir, pipeline.state
            )
            self.assertIsNotNone(pack_path)
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertEqual(2, len(pack["evidence"]))

    def test_recording_endpoint_uses_one_causally_changed_pack_fallback(self) -> None:
        state = {
            "fallback_chain": [],
            "recording_recovery": {"outcome": "pass"},
        }
        fallback = MODULE.evidence_pack_fallback_entry(state, "recording")
        self.assertEqual("fallback-001", fallback["fallback_id"])
        self.assertEqual(
            "target_verified_endpoint_evidence_pack",
            fallback["to_strategy"],
        )
        self.assertIn("instead of retrying recording", fallback["changed_condition"])

    def test_stage_precedence_avoids_diagnostic_substring_false_positives(self) -> None:
        self.assertEqual("RECORDING_FAILED", MODULE.classify_failure("recording", "failed to stop recording"))
        self.assertEqual(
            "SEQUENCE_COVERAGE",
            MODULE.classify_failure("sequence_selection", 'near_black_ratio: 0.0; accepted_sequence_does_not_cover_expected_progress'),
        )
        self.assertEqual(
            "SNAPSHOT_NOT_TOP",
            MODULE.classify_failure("snapshot_and_plan", "Main scroll container is not at the top: 43.0%"),
        )

    def test_pipeline_initializes_versioned_identity_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(
                output=str(root / "output.png"),
                before_screenshot=str(root / "before.png"),
                work_dir=str(root / "work"),
                run_id="run-test",
                case_id="CSI-CASE-005",
                variant="candidate",
                expected_bundle="example.bundle",
                session="phone-main",
                capture_extent="auto",
            )
            pipeline = MODULE.Pipeline(args)
            for key in ("schema_version", "run_id", "case_id", "skill_hash", "variant", "started_at", "environment", "attempts", "fallback_chain", "final_task_result", "completed_stages", "metrics"):
                self.assertIn(key, pipeline.state)
            self.assertEqual(1, pipeline.state["schema_version"])
            self.assertEqual("candidate", pipeline.state["variant"])
            self.assertEqual(64, len(pipeline.state["skill_hash"]))

    def test_completed_stage_is_persisted_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(
                output=str(root / "output.png"),
                before_screenshot=str(root / "before.png"),
                work_dir=str(root / "work"),
                run_id="run-stage-test",
                case_id="CSI-CASE-005",
                variant="candidate",
                expected_bundle="example.bundle",
                session="phone-main",
                capture_extent="auto",
            )
            pipeline = MODULE.Pipeline(args)
            pipeline.reporting_ready = True
            self.assertEqual("ok", pipeline.stage("snapshot_and_plan", lambda: "ok"))
            self.assertEqual(["snapshot_and_plan"], pipeline.state["completed_stages"])

    def test_evidence_pack_deduplicates_and_rejects_black_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            accepted = work / "accepted"
            accepted.mkdir()
            valid = np.full((120, 80, 3), 180, dtype=np.uint8)
            black = np.zeros((120, 80, 3), dtype=np.uint8)
            cv2.imwrite(str(accepted / "segment-000.png"), valid)
            cv2.imwrite(str(accepted / "segment-001.png"), valid)
            cv2.imwrite(str(accepted / "segment-002.png"), black)
            state = {
                "target_verified": True,
                "run_id": "run-test",
                "case_id": "CSI-CASE-005",
                "expected_bundle": "example.bundle",
                "capture_strategy": "adaptive_still",
                "current_stage": "adaptive_still_qa",
                "failure": {"code": "STITCH_QA"},
                "geometry": {"crops": {"top_crop": 0, "bottom_crop": 0, "x_margin": 0}},
            }
            pack_path = MODULE.build_viewport_evidence_pack(work, state)
            self.assertIsNotNone(pack_path)
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertEqual(1, len(pack["evidence"]))
            self.assertTrue(pack["evidence"][0]["quality"]["hard_pass"])

    def test_evidence_pack_requires_verified_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(MODULE.build_viewport_evidence_pack(Path(directory), {"target_verified": False}))


class SemanticFallbackTests(unittest.TestCase):
    def derive(self, nodes: list[dict]) -> dict:
        return MODULE.derive_scroll_plan(
            {"data": {"nodes": nodes}},
            1170,
            2532,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    def test_media_only_collection_is_not_selected_over_page_container(self) -> None:
        nodes = [
            {
                "index": 0,
                "type": "Application",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
            },
            {
                "index": 1,
                "parentIndex": 0,
                "type": "ScrollView",
                "identifier": "property_details",
                "hiddenContentBelow": True,
                "rect": {"x": 0, "y": 80, "width": 390, "height": 764},
            },
            {
                "index": 2,
                "parentIndex": 1,
                "type": "StaticText",
                "label": "Entire home in Osaka",
                "rect": {"x": 20, "y": 500, "width": 300, "height": 40},
            },
            {
                "index": 10,
                "parentIndex": 1,
                "type": "CollectionView",
                "label": "Photo gallery",
                "hiddenContentBelow": True,
                "rect": {"x": 0, "y": 80, "width": 390, "height": 700},
            },
            {
                "index": 11,
                "parentIndex": 10,
                "type": "Cell",
                "rect": {"x": 0, "y": 80, "width": 390, "height": 330},
            },
            {
                "index": 12,
                "parentIndex": 11,
                "type": "Image",
                "label": "Property photo 1",
                "rect": {"x": 0, "y": 80, "width": 390, "height": 330},
            },
            {
                "index": 13,
                "parentIndex": 10,
                "type": "Cell",
                "rect": {"x": 0, "y": 430, "width": 390, "height": 330},
            },
            {
                "index": 14,
                "parentIndex": 13,
                "type": "Image",
                "label": "Property photo 2",
                "rect": {"x": 0, "y": 430, "width": 390, "height": 330},
            },
            {
                "index": 15,
                "parentIndex": 10,
                "type": "Other",
                "label": "Vertical scroll bar, 5 pages",
                "rect": {"x": 386, "y": 80, "width": 4, "height": 700},
            },
        ]
        plan = self.derive(nodes)
        self.assertEqual(1, plan["scroll_node"]["index"])
        gallery = next(item for item in plan["scroll_candidates"] if item["index"] == 10)
        self.assertFalse(gallery["eligible"])
        self.assertEqual("media_only", gallery["container_role"])
        self.assertEqual(
            "media_only_collection_is_not_page_container",
            gallery["rejection_reason"],
        )

    def test_collection_backed_media_led_detail_remains_capturable(self) -> None:
        nodes = [
            {
                "index": 0,
                "type": "Application",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
            },
            {
                "index": 1,
                "parentIndex": 0,
                "type": "CollectionView",
                "label": "1 of 26 photos, Osaka apartment image 1",
                "hiddenContentBelow": True,
                "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
            },
            {
                "index": 2,
                "parentIndex": 1,
                "type": "Cell",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 360},
            },
            {
                "index": 3,
                "parentIndex": 2,
                "type": "Image",
                "label": "Osaka apartment photo 1",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 360},
            },
            {
                "index": 4,
                "parentIndex": 1,
                "type": "Cell",
                "label": "Entire rental unit in Osaka, Japan",
                "rect": {"x": 0, "y": 380, "width": 390, "height": 100},
            },
            {
                "index": 5,
                "parentIndex": 1,
                "type": "Cell",
                "label": "Rated 4.89 out of 5 stars, 5,726 reviews",
                "rect": {"x": 0, "y": 500, "width": 390, "height": 100},
            },
            {
                "index": 6,
                "parentIndex": 1,
                "type": "Cell",
                "label": "Self check-in with the lockbox",
                "rect": {"x": 0, "y": 650, "width": 390, "height": 100},
            },
            {
                "index": 7,
                "parentIndex": 1,
                "type": "Other",
                "label": "Vertical scroll bar, 8 pages",
                "rect": {"x": 386, "y": 20, "width": 4, "height": 760},
            },
        ]
        plan = self.derive(nodes)
        self.assertEqual(1, plan["scroll_node"]["index"])
        self.assertEqual("media_led_detail", plan["container_role"])
        self.assertIsNone(plan["container_role_warning"])
        selected = next(item for item in plan["scroll_candidates"] if item["selected"])
        self.assertEqual(3, selected["business_content_cell_count"])
        self.assertEqual(1, selected["media_cell_count"])

    def test_ambiguous_media_container_is_recorded_and_uses_viewport_strategy(self) -> None:
        nodes = [
            {
                "index": 0,
                "type": "Application",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
            },
            {
                "index": 1,
                "parentIndex": 0,
                "type": "CollectionView",
                "label": "Gallery and details",
                "hiddenContentBelow": True,
                "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
            },
            {
                "index": 2,
                "parentIndex": 1,
                "type": "Cell",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 600},
            },
            {
                "index": 3,
                "parentIndex": 2,
                "type": "Image",
                "label": "Gallery photo",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 600},
            },
            {
                "index": 4,
                "parentIndex": 1,
                "type": "Cell",
                "label": "Property overview",
                "rect": {"x": 0, "y": 620, "width": 390, "height": 100},
            },
            {
                "index": 5,
                "parentIndex": 1,
                "type": "Other",
                "label": "Vertical scroll bar, 6 pages",
                "rect": {"x": 386, "y": 20, "width": 4, "height": 760},
            },
            {
                "index": 6,
                "parentIndex": 5,
                "type": "Other",
                "rect": {"x": 386, "y": 20, "width": 4, "height": 100},
            },
        ]
        plan = self.derive(nodes)
        self.assertEqual("ambiguous_media_container", plan["container_role"])
        self.assertEqual(
            "main_container_media_identity_ambiguous",
            plan["container_role_warning"],
        )
        self.assertEqual("unknown", plan["height_confidence"])
        self.assertEqual("adaptive_still", plan["capture_strategy"])
        self.assertEqual(
            "ambiguous_media_identity_prefers_viewport_evidence",
            plan["capture_strategy_reason"],
        )

    def test_large_result_count_scroll_view_is_not_treated_as_complete_page(self) -> None:
        snapshot = {
            "data": {
                "nodes": [
                    {
                        "index": 0,
                        "type": "Application",
                        "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
                    },
                    {
                        "index": 1,
                        "parentIndex": 0,
                        "type": "ScrollView",
                        "label": "993 flights found",
                        "identifier": "flights_search_results_results_list",
                        "rect": {"x": 0, "y": 220, "width": 390, "height": 624},
                    },
                    {
                        "index": 2,
                        "parentIndex": 1,
                        "type": "Other",
                        "label": "993 flights found",
                        "rect": {"x": 0, "y": 220, "width": 390, "height": 3570},
                    },
                    {
                        "index": 3,
                        "parentIndex": 1,
                        "type": "Other",
                        "label": "Vertical scroll bar, 6 pages",
                        "value": "0%",
                        "rect": {"x": 357, "y": 220, "width": 30, "height": 577},
                    },
                ]
            }
        }
        plan = MODULE.derive_scroll_plan(
            snapshot,
            1170,
            2532,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        self.assertEqual(993, plan["semantic_results_total"])
        self.assertEqual("unknown", plan["height_confidence"])
        self.assertEqual("adaptive_still", plan["capture_strategy"])
        self.assertEqual(
            "large_result_count_not_treated_as_bounded",
            plan["height_warning"],
        )

    def test_virtualized_table_thumb_ratio_routes_to_adaptive_still(self) -> None:
        snapshot = {
            "data": {
                "nodes": [
                    {
                        "index": 0,
                        "type": "Application",
                        "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
                    },
                    {
                        "index": 1,
                        "parentIndex": 0,
                        "type": "Table",
                        "hiddenContentBelow": True,
                        "rect": {"x": 0, "y": 162, "width": 390, "height": 682},
                    },
                    {
                        "index": 2,
                        "parentIndex": 1,
                        "type": "Cell",
                        "rect": {"x": 0, "y": 162, "width": 390, "height": 200},
                    },
                    {
                        "index": 3,
                        "parentIndex": 1,
                        "type": "Cell",
                        "rect": {"x": 0, "y": 382, "width": 390, "height": 200},
                    },
                    {
                        "index": 4,
                        "parentIndex": 1,
                        "type": "Cell",
                        "rect": {"x": 0, "y": 602, "width": 390, "height": 200},
                    },
                    {
                        "index": 5,
                        "parentIndex": 1,
                        "type": "Other",
                        "label": "Vertical scroll bar, 44 pages",
                        "value": "0%",
                        "rect": {"x": 386, "y": 162, "width": 4, "height": 682},
                    },
                    {
                        "index": 6,
                        "parentIndex": 5,
                        "type": "Other",
                        "rect": {"x": 386, "y": 162, "width": 4, "height": 40},
                    },
                ]
            }
        }
        plan = MODULE.derive_scroll_plan(
            snapshot,
            1170,
            2532,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        self.assertEqual(
            "virtualized_container_height_not_treated_as_bounded",
            plan["height_warning"],
        )
        self.assertEqual("unknown", plan["height_confidence"])
        self.assertEqual("adaptive_still", plan["capture_strategy"])
        self.assertEqual(
            "virtualized_loaded_cell_window_is_not_a_bounded_height",
            plan["capture_strategy_reason"],
        )

    def test_page_count_only_height_routes_virtual_list_to_adaptive_still(self) -> None:
        snapshot = {
            "data": {
                "nodes": [
                    {
                        "index": 0,
                        "type": "Application",
                        "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
                    },
                    {
                        "index": 1,
                        "parentIndex": 0,
                        "type": "Table",
                        "hiddenContentBelow": True,
                        "rect": {"x": 0, "y": 162, "width": 390, "height": 682},
                    },
                    {
                        "index": 2,
                        "parentIndex": 1,
                        "type": "Cell",
                        "rect": {"x": 0, "y": 162, "width": 390, "height": 200},
                    },
                    {
                        "index": 3,
                        "parentIndex": 1,
                        "type": "Cell",
                        "rect": {"x": 0, "y": 382, "width": 390, "height": 200},
                    },
                    {
                        "index": 4,
                        "parentIndex": 1,
                        "type": "Cell",
                        "rect": {"x": 0, "y": 602, "width": 390, "height": 200},
                    },
                    {
                        "index": 5,
                        "parentIndex": 1,
                        "type": "Other",
                        "label": "Vertical scroll bar, 4 pages",
                        "value": "0%",
                        "rect": {"x": 386, "y": 162, "width": 4, "height": 682},
                    },
                ]
            }
        }
        plan = MODULE.derive_scroll_plan(
            snapshot,
            1170,
            2532,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        self.assertEqual(
            "content_height_uses_accessibility_page_count_fallback",
            plan["height_warning"],
        )
        self.assertEqual("unknown", plan["height_confidence"])
        self.assertEqual("adaptive_still", plan["capture_strategy"])
        self.assertEqual(
            "accessibility_page_count_only_is_not_a_bounded_height",
            plan["capture_strategy_reason"],
        )

    def test_no_nodes_requests_coordinate_fallback(self) -> None:
        with self.assertRaises(MODULE.SemanticFallbackRequired) as caught:
            MODULE.derive_scroll_plan(
                {"data": {"nodes": []}},
                1170,
                2532,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        self.assertEqual(caught.exception.trigger, "no_nodes")

    def test_current_position_can_be_used_for_command_long_capture(self) -> None:
        snapshot = {
            "data": {
                "nodes": [
                    {
                        "index": 0,
                        "type": "Application",
                        "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
                    },
                    {
                        "index": 1,
                        "parentIndex": 0,
                        "type": "ScrollView",
                        "hiddenContentBelow": True,
                        "rect": {"x": 0, "y": 80, "width": 390, "height": 764},
                    },
                    {
                        "index": 2,
                        "parentIndex": 1,
                        "type": "StaticText",
                        "label": "Current page business content",
                        "rect": {"x": 20, "y": 500, "width": 300, "height": 40},
                    },
                    {
                        "index": 3,
                        "parentIndex": 1,
                        "type": "Other",
                        "label": "Vertical scroll bar, 5 pages",
                        "value": "43%",
                        "rect": {"x": 386, "y": 80, "width": 4, "height": 764},
                    },
                ]
            }
        }
        with self.assertRaises(MODULE.PipelineError):
            self.derive(snapshot["data"]["nodes"])
        plan = MODULE.derive_scroll_plan(
            snapshot,
            1170,
            2532,
            None,
            None,
            None,
            None,
            None,
            None,
            require_top=False,
        )
        self.assertEqual(43.0, plan["scroll_position_percent"])
        self.assertEqual("capture_started_below_top:43.0%", plan["position_warning"])

    def test_zero_sized_root_requests_coordinate_fallback(self) -> None:
        snapshot = {
            "data": {
                "nodes": [
                    {
                        "index": 0,
                        "type": "Application",
                        "rect": {"x": 0, "y": 0, "width": 0, "height": 0},
                    }
                ]
            }
        }
        with self.assertRaises(MODULE.SemanticFallbackRequired) as caught:
            MODULE.derive_scroll_plan(
                snapshot,
                1170,
                2532,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        self.assertEqual(caught.exception.trigger, "invalid_root_dimensions")

    def test_valid_semantics_without_main_container_use_coordinate_fallback(self) -> None:
        snapshot = {
            "data": {
                "nodes": [
                    {
                        "index": 0,
                        "type": "Application",
                        "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
                    },
                    {
                        "index": 1,
                        "parentIndex": 0,
                        "type": "Button",
                        "rect": {"x": 20, "y": 100, "width": 100, "height": 44},
                    },
                ]
            }
        }
        with self.assertRaises(MODULE.SemanticFallbackRequired) as caught:
            MODULE.derive_scroll_plan(
                snapshot,
                1170,
                2532,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        self.assertEqual("no_main_scroll_container", caught.exception.trigger)
        self.assertIn("Unable to identify", str(caught.exception))

    def test_only_timeout_errors_are_classified_as_snapshot_timeout(self) -> None:
        self.assertTrue(
            MODULE.is_semantic_snapshot_timeout(
                MODULE.PipelineError("snapshot failed: XCTest timed out")
            )
        )
        self.assertFalse(
            MODULE.is_semantic_snapshot_timeout(
                MODULE.PipelineError("snapshot failed: device disconnected")
            )
        )

    def test_visual_coordinate_plan_uses_adaptive_still(self) -> None:
        plan = MODULE.build_visual_coordinate_plan(
            1170,
            2532,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        self.assertEqual(plan["geometry_source"], "visual_coordinate_fallback")
        self.assertEqual(plan["capture_strategy"], "adaptive_still")
        self.assertEqual(plan["height_confidence"], "unknown")
        self.assertEqual(plan["root_rect"]["width"], 390)
        self.assertEqual(plan["root_rect"]["height"], 844)
        self.assertEqual(plan["gesture"], {"x": 195, "y": 650, "dx": 0, "dy": -390})
        self.assertEqual(plan["crops"]["top_crop"], 557)
        self.assertEqual(plan["crops"]["bottom_crop"], 380)

    def test_visual_coordinate_plan_rejects_unconfigured_aspect_ratio(self) -> None:
        with self.assertRaises(MODULE.PipelineError):
            MODULE.build_visual_coordinate_plan(
                2532,
                1170,
                None,
                None,
                None,
                None,
                None,
                None,
            )


class GestureGeometryTests(unittest.TestCase):
    def test_full_width_scroll_container_uses_screen_center(self) -> None:
        self.assertEqual(
            MODULE.centered_gesture_x(
                {"x": 0, "y": 0, "width": 390, "height": 844},
                {"x": 0, "y": 151, "width": 390, "height": 610},
            ),
            195,
        )

    def test_inset_scroll_container_uses_shared_center(self) -> None:
        self.assertEqual(
            MODULE.centered_gesture_x(
                {"x": 0, "y": 0, "width": 390, "height": 844},
                {"x": 40, "y": 100, "width": 300, "height": 600},
            ),
            190,
        )


if __name__ == "__main__":
    unittest.main()
