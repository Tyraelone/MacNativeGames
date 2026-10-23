import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "games/totk/scripts/analyze_nvn_bindings.py"


def load_analyzer():
    spec = importlib.util.spec_from_file_location("analyze_nvn_bindings", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BindTraceTests(unittest.TestCase):
    def test_reports_stage_masks_without_leaking_program_addresses(self):
        log = [
            "noise [bindprog] frame=7 mask=0x3 prog=0x123456 serial=10 nstage=2 data0=0x99 chain: main+0x111 "
            "[bindprog] frame=7 mask=0x3c prog=0x0 serial=0 nstage=0 data0=0 chain: main+0x222\n",
            "[bindprog] frame=8 mask=0x20 prog=0xabcdef serial=11 nstage=1 data0=0 chain: sdk+0x333\n",
            "[bindprog] frame=8 mask=0x1 prog=0x9876 serial=12 nstage=1 data0=0\n",
            "[bindprog] frame=8 mask=0x40 prog=0x9876 serial=12 nstage=1 data0=0\n",
            "[bindprog] frame=8 mask=broken prog=0x0 serial=0 nstage=0\n",
        ]
        result = load_analyzer().analyze_lines(log)
        self.assertEqual(result["records"], 5)
        self.assertEqual(result["malformed_records"], 1)
        self.assertEqual(result["frames"], {"first": 7, "last": 8})
        self.assertEqual(result["masks"]["0x3"], {"program": 1, "null": 0})
        self.assertEqual(result["masks"]["0x3c"], {"program": 0, "null": 1})
        self.assertEqual(result["graphics_then_non_graphics_null"], 1)
        self.assertEqual(result["partial_graphics_records"], 1)
        self.assertEqual(result["compute_program_records"], 1)
        self.assertEqual(result["unknown_bit_records"], 1)
        self.assertEqual(result["divergent_graphics_transitions"], 1)
        self.assertEqual(result["example_lines"], {
            "partial_graphics": [3], "unknown_bits": [4], "malformed": [5],
            "divergent_graphics": [3], "incomplete_graphics": [],
        })
        encoded = json.dumps(result)
        self.assertNotIn("0x123456", encoded)
        self.assertNotIn("main+0x111", encoded)

    def test_cli_reads_external_log_and_reports_sample_limit(self):
        record = "[bindprog] frame=2 mask=0x3 prog=0x1 serial=9 nstage=2 data0=0\n"
        with tempfile.TemporaryDirectory(prefix="mng-bind-log-") as folder:
            log_path = Path(folder) / "bindings.log"
            log_path.write_text(record * 20000)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(log_path)],
                capture_output=True, text=True, check=True,
            )
        report = json.loads(result.stdout)
        self.assertEqual(report["records"], 20000)
        self.assertTrue(report["logger_record_limit_reached"])
        self.assertIn("sample", report["coverage_note"])

    def test_malformed_logger_record_still_counts_toward_log_cap(self):
        record = "[bindprog] frame=2 mask=0x3 prog=0x1 serial=9 nstage=2\n"
        malformed = "[bindprog] incomplete\n"
        report = load_analyzer().analyze_lines([record] * 19999 + [malformed])
        self.assertEqual(report["records"], 19999)
        self.assertEqual(report["malformed_records"], 1)
        self.assertTrue(report["logger_record_limit_reached"])

    def test_tracks_selected_shader_stages_and_incomplete_graphics(self):
        log = [
            "[bindprog] frame=4 mask=0x3 prog=0xa serial=1 nstage=2\n",
            "[bindprog] frame=4 mask=0x20 prog=0xb serial=2 nstage=1\n",
            "[bindprog] frame=4 mask=0x2 prog=0x0 serial=0 nstage=0\n",
            "[bindprog] frame=4 mask=0x2 prog=0xa serial=1 nstage=2\n",
        ]
        report = load_analyzer().analyze_lines(log)
        self.assertEqual(report["divergent_graphics_transitions"], 0)
        self.assertEqual(report["incomplete_graphics_transitions"], 1)
        self.assertEqual(report["example_lines"]["incomplete_graphics"], [3])

    def test_stage_sources_use_program_serial_as_well_as_pointer(self):
        log = [
            "[bindprog] frame=9 mask=0x3 prog=0xa serial=1 nstage=2\n",
            "[bindprog] frame=9 mask=0x2 prog=0xa serial=2 nstage=1\n",
        ]
        report = load_analyzer().analyze_lines(log)
        self.assertEqual(report["divergent_graphics_transitions"], 1)


if __name__ == "__main__":
    unittest.main()
