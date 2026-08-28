from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "rebuild_from_evidence_pack.py"
SPEC = importlib.util.spec_from_file_location("rebuild_from_evidence_pack", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def evidence(count: int) -> list[dict[str, object]]:
    return [{"evidence_id": f"viewport-{index + 1:03d}", "capture_order": index + 1} for index in range(count)]


class CausalRetrySelectionTests(unittest.TestCase):
    def test_drops_later_frame_for_each_low_confidence_seam(self) -> None:
        retained, dropped = MODULE.select_causal_retry_evidence(evidence(6), [1, 3])
        self.assertEqual([1, 3, 5, 6], [item["capture_order"] for item in retained])
        self.assertEqual(["viewport-002", "viewport-004"], dropped)

    def test_preserves_last_endpoint_for_final_seam(self) -> None:
        retained, dropped = MODULE.select_causal_retry_evidence(evidence(6), [5])
        self.assertEqual([1, 2, 3, 4, 6], [item["capture_order"] for item in retained])
        self.assertEqual(["viewport-005"], dropped)

    def test_refuses_retry_when_too_few_viewports_would_remain(self) -> None:
        original = evidence(3)
        retained, dropped = MODULE.select_causal_retry_evidence(original, [1])
        self.assertEqual(original, retained)
        self.assertEqual([], dropped)


if __name__ == "__main__":
    unittest.main()
