"""Opt-in Mario gameplay frame-time regression using an isolated, recorded run.

Set MARIO_PERF_TSV and the movement frame bounds after driving a test save.
The game, save, cache and TSV must all live outside the source tree.
"""

import os
from pathlib import Path
import unittest

from game_tools.frame_metrics import summarize_tsv


@unittest.skipUnless(os.environ.get("MARIO_PERF_TSV"), "requires an isolated Mario gameplay recording")
class MarioMovementPerformanceTests(unittest.TestCase):
    def test_movement_does_not_block_on_new_metal_compilation(self):
        path = Path(os.environ["MARIO_PERF_TSV"]).resolve()
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn(root, path.parents)
        first = int(os.environ["MARIO_PERF_FIRST"])
        last = int(os.environ["MARIO_PERF_LAST"])
        self.assertGreaterEqual(last - first, 300)
        report = summarize_tsv(path, first, last, budget_ms=100.0)
        self.assertTrue(report["complete_frame_coverage"], report)
        self.assertLess(report["frame_ms_p99"], 50.0, report)
        self.assertLess(report["frame_ms_max"], 100.0, report)


if __name__ == "__main__":
    unittest.main()
