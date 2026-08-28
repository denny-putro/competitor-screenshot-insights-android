from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "screenshot_checks.py"
SPEC = importlib.util.spec_from_file_location("screenshot_checks", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TargetContinuityIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.before = self.root / "before.png"
        self.after = self.root / "after.png"
        self.expected_bundle = "com.example.target"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def images(
        self,
        body_mode: str,
        top_chrome_same: bool = True,
        bottom_chrome_same: bool = True,
    ) -> None:
        height, width = 844, 390
        before = np.full((height, width, 3), 244, dtype=np.uint8)
        cv2.rectangle(before, (0, 34), (width, 200), (230, 238, 248), -1)
        cv2.rectangle(before, (20, 70), (250, 120), (80, 110, 190), -1)
        cv2.rectangle(before, (270, 70), (365, 120), (40, 80, 150), -1)
        for index, y in enumerate((230, 390, 550)):
            cv2.rectangle(before, (20, y), (370, y + 120), (210 - index * 15, 220, 235), -1)
            cv2.rectangle(before, (35, y + 15), (135, y + 105), (100, 130 + index * 15, 170), -1)
            cv2.line(before, (155, y + 35), (350, y + 35), (40, 50, 60), 8)
            cv2.line(before, (155, y + 75), (320, y + 75), (80, 90, 100), 6)
        after = before.copy()
        rng = np.random.default_rng(42)
        if body_mode == "dynamic":
            after[200:744] = np.clip(
                after[200:744].astype(np.int16) - 12, 0, 255
            ).astype(np.uint8)
            after[245:350, 35:135] = rng.integers(40, 220, (105, 100, 3), dtype=np.uint8)
            after[405:510, 35:135] = rng.integers(40, 220, (105, 100, 3), dtype=np.uint8)
            after[565:670, 35:135] = rng.integers(40, 220, (105, 100, 3), dtype=np.uint8)
        elif body_mode == "different":
            after[200:744] = rng.integers(0, 255, (544, width, 3), dtype=np.uint8)
        if not top_chrome_same:
            after[34:200] = rng.integers(0, 255, (166, width, 3), dtype=np.uint8)
        if not bottom_chrome_same:
            after[744:832] = rng.integers(0, 255, (88, width, 3), dtype=np.uint8)
        cv2.imwrite(str(self.before), before)
        cv2.imwrite(str(self.after), after)

    def args(self, continuity_mode: str = "read-only") -> argparse.Namespace:
        return argparse.Namespace(
            agent_device="fixture-agent-device",
            session="fixture-session",
            expected_bundle=self.expected_bundle,
            before_screenshot=str(self.before),
            after_screenshot=str(self.after),
            top_crop=200,
            bottom_crop=100,
            x_margin=10,
            min_visual_similarity=0.97,
            min_visual_hash_similarity=0.90,
            min_chrome_similarity=0.97,
            min_chrome_hash_similarity=0.90,
            min_dynamic_body_similarity=0.84,
            min_dynamic_body_hash_similarity=0.70,
            continuity_mode=continuity_mode,
        )

    def run_check(
        self,
        *,
        reported_bundle: str | None = None,
        continuity_mode: str = "read-only",
    ) -> tuple[int, dict]:
        state = {
            "success": True,
            "data": {
                "appBundleId": reported_bundle or self.expected_bundle,
                "appName": reported_bundle or self.expected_bundle,
                "source": "session",
                "surface": "app",
            },
        }
        completed = subprocess.CompletedProcess(
            ["fixture-agent-device"], 0, json.dumps(state), None
        )
        output = io.StringIO()
        with patch.object(MODULE.subprocess, "run", return_value=completed):
            with redirect_stdout(output):
                code = MODULE.check_target_app(self.args(continuity_mode))
        return code, json.loads(output.getvalue())

    def test_dynamic_body_with_stable_chrome_and_exact_bundle_passes_with_warning(self) -> None:
        self.images("dynamic")
        before = MODULE.load_image(str(self.before))
        after = MODULE.load_image(str(self.after))
        metrics = MODULE.similarity_metrics(before[200:744, 10:-10], after[200:744, 10:-10])
        self.assertLess(metrics["pixel_similarity"], 0.97)
        self.assertGreaterEqual(metrics["pixel_similarity"], 0.84)
        self.assertGreaterEqual(metrics["dhash_similarity"], 0.70)
        code, payload = self.run_check()
        self.assertEqual(MODULE.EXIT_PASS, code)
        self.assertEqual("accept_with_warnings", payload["decision"])
        self.assertEqual("stable_app_chrome_with_dynamic_body", payload["reason"])
        self.assertTrue(payload["visual_identity"]["stable_chrome"])

    def test_bundle_mismatch_remains_a_hard_reject(self) -> None:
        self.images("dynamic")
        code, payload = self.run_check(reported_bundle="com.example.other")
        self.assertEqual(MODULE.EXIT_FAIL, code)
        self.assertEqual("target_bundle_mismatch", payload["reason"])

    def test_unrelated_body_is_not_excused_in_read_only_mode(self) -> None:
        self.images("different")
        code, payload = self.run_check()
        self.assertEqual(MODULE.EXIT_FAIL, code)
        self.assertEqual(
            "unexpected_visual_change_during_read_only_observation",
            payload["reason"],
        )

    def test_scrolled_endpoint_accepts_stable_top_chrome(self) -> None:
        self.images("different")
        code, payload = self.run_check(continuity_mode="scrolled")
        self.assertEqual(MODULE.EXIT_PASS, code)
        self.assertEqual(
            "stable_app_chrome_with_expected_scroll_progress",
            payload["reason"],
        )
        self.assertEqual("top", payload["visual_identity"]["stable_chrome_source"])

    def test_scrolled_endpoint_accepts_stable_bottom_chrome_when_top_folds(self) -> None:
        self.images("different", top_chrome_same=False)
        code, payload = self.run_check(continuity_mode="scrolled")
        self.assertEqual(MODULE.EXIT_PASS, code)
        self.assertEqual("bottom", payload["visual_identity"]["stable_chrome_source"])

    def test_scrolled_endpoint_rejects_when_both_chrome_regions_change(self) -> None:
        self.images(
            "different",
            top_chrome_same=False,
            bottom_chrome_same=False,
        )
        code, payload = self.run_check(continuity_mode="scrolled")
        self.assertEqual(MODULE.EXIT_FAIL, code)
        self.assertEqual(
            "unexpected_visual_change_during_read_only_observation",
            payload["reason"],
        )


if __name__ == "__main__":
    unittest.main()
