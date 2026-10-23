"""Offline NVN frame summaries use synthetic TSV, never player logs."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "game_tools/frame_metrics.py"


class FrameMetricsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mng-frame-metrics-")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "frames.tsv"

    def test_complete_distribution_exposes_missing_and_invalid_frames(self):
        from game_tools.frame_metrics import summarize_tsv
        self.path.write_text(
            "10\t@frame_ms\t10\n11\t@frame_ms\t20\n12\t@frame_ms\t30\n"
            "13\t@frame_ms\tnan\n14\t@frame_ms\t40\n"
            "10\t@gpu_ms\t2\n11\t@gpu_ms\t4\n"
            "12\t@pso_new\t2\n14\t@pso_new\t1\n"
            "99\t@frame_ms\t999\n12\t@draws\t700\n"
        )
        report = summarize_tsv(self.path, 10, 14, budget_ms=16.0)
        self.assertEqual((report["expected_frames"], report["measured_frames"],
                          report["missing_frame_count"], report["invalid_rows"]), (5, 4, 1, 1))
        self.assertEqual((report["frame_ms_p50"], report["frame_ms_p95"],
                          report["frame_ms_p99"], report["frame_ms_max"]),
                         (20.0, 40.0, 40.0, 40.0))
        self.assertEqual(report["fps_mean"], 40.0)
        self.assertEqual((report["over_budget_frames"], report["over_budget_fraction"]), (3, .75))
        self.assertEqual((report["gpu_measured_frames"], report["gpu_ms_p50"],
                          report["gpu_ms_p95"], report["pso_measured_frames"],
                          report["pso_new_total"]), (2, 2.0, 4.0, 2, 3.0))
        self.assertFalse(report["complete_frame_coverage"])

    def test_absent_gpu_and_pipeline_samples_remain_unknown(self):
        from game_tools.frame_metrics import summarize_tsv
        self.path.write_text("1\t@frame_ms\t16\n")
        report = summarize_tsv(self.path, 1, 1)
        self.assertTrue(report["complete_frame_coverage"])
        self.assertEqual(report["gpu_measured_frames"], 0)
        self.assertIsNone(report["gpu_ms_p50"])
        self.assertEqual(report["pso_measured_frames"], 0)
        self.assertIsNone(report["pso_new_total"])

    def test_duplicate_metric_rejected(self):
        from game_tools.frame_metrics import summarize_tsv
        self.path.write_text("7\t@frame_ms\t10\n7\t@frame_ms\t10\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            summarize_tsv(self.path, 7, 7)

    def test_malformed_selected_rows_count_as_invalid_samples(self):
        from game_tools.frame_metrics import summarize_tsv
        self.path.write_text(
            "1\t@frame_ms\t10\n"
            "2\t@frame_ms\n"
            "3\t@frame_ms\t12\textra\n"
            "1\t@gpu_ms\n"
            "2\t@draws\n"
        )
        report = summarize_tsv(self.path, 1, 3)
        self.assertEqual(report["invalid_rows"], 3)
        self.assertEqual(report["invalid_frame_rows"], 2)
        self.assertEqual(report["missing_frame_count"], 2)
        self.assertFalse(report["complete_frame_coverage"])

    def test_cli_and_old_scene_script_share_summary(self):
        self.path.write_text("1\t@frame_ms\t10\n2\t@frame_ms\t30\n2\t@gpu_ms\t4\n")
        command = [sys.executable, str(SCRIPT), str(self.path), "--first", "1", "--last", "2",
                   "--budget-ms", "20"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        cli = json.loads(result.stdout)
        self.assertEqual(cli["frame_ms_p95"], 30.0)
        self.assertEqual(cli["over_budget_frames"], 1)
        self.assertEqual(sorted(path.name for path in self.path.parent.iterdir()), ["frames.tsv"])

        path = ROOT / "games/totk/scripts/mac_v143_smoke.py"
        spec = importlib.util.spec_from_file_location("mac_v143_smoke", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        scene = module.summarize(self.path, 1, 2)
        self.assertEqual(scene["frame_ms_p95"], 30.0)
        self.assertEqual(scene["over_budget_frames"], 1)
        self.assertIn("fixed camera", scene["scope"])

    def test_copied_scene_script_finds_shared_metrics(self):
        self.path.write_text("1\t@frame_ms\t10\n2\t@frame_ms\t30\n")
        work = self.path.parent / "work"
        scripts = work / "totk/scripts"
        (scripts / "dev").mkdir(parents=True)
        shared = work / "game_tools"
        shared.mkdir()
        shutil.copy2(ROOT / "games/totk/scripts/mac_v143_smoke.py", scripts)
        shutil.copy2(ROOT / "games/totk/scripts/dev/game_slot.py", scripts / "dev")
        shutil.copy2(ROOT / "game_tools/__init__.py", shared)
        shutil.copy2(SCRIPT, shared)
        code = ("import importlib.util,sys; "
                "s=importlib.util.spec_from_file_location('scene',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "print(m.summarize(__import__('pathlib').Path(sys.argv[2]),1,2)['frame_ms_p95'])")
        result = subprocess.run([sys.executable, "-c", code, str(scripts / "mac_v143_smoke.py"),
                                 str(self.path)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "30.0")


if __name__ == "__main__":
    unittest.main()
