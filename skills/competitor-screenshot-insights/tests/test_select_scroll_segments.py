from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "select_scroll_segments.py"
)
SPEC = importlib.util.spec_from_file_location("select_scroll_segments", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisualTerminalTests(unittest.TestCase):
    def test_two_no_progress_signals_override_low_semantic_coverage(self) -> None:
        self.assertTrue(
            MODULE.visual_terminal_is_complete(
                bottom_confirmed_no_progress=True,
                sequence_confirmed_no_progress=True,
                cumulative_progress_px=900,
                coverage_ratio=0.35,
                minimum_coverage_ratio=0.80,
            )
        )

    def test_bottom_duplicate_alone_does_not_override_low_coverage(self) -> None:
        self.assertFalse(
            MODULE.visual_terminal_is_complete(
                bottom_confirmed_no_progress=True,
                sequence_confirmed_no_progress=False,
                cumulative_progress_px=900,
                coverage_ratio=0.35,
                minimum_coverage_ratio=0.80,
            )
        )

    def test_no_progress_without_accepted_scroll_is_not_a_bottom(self) -> None:
        self.assertFalse(
            MODULE.visual_terminal_is_complete(
                bottom_confirmed_no_progress=True,
                sequence_confirmed_no_progress=True,
                cumulative_progress_px=0,
                coverage_ratio=0,
                minimum_coverage_ratio=0.80,
            )
        )

    def test_existing_high_coverage_behavior_is_preserved(self) -> None:
        self.assertTrue(
            MODULE.visual_terminal_is_complete(
                bottom_confirmed_no_progress=True,
                sequence_confirmed_no_progress=False,
                cumulative_progress_px=850,
                coverage_ratio=0.85,
                minimum_coverage_ratio=0.80,
            )
        )


if __name__ == "__main__":
    unittest.main()
