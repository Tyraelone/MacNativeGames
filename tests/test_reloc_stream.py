"""The C relocation iterator reads only immutable, bounded source tables."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc") or shutil.which("clang"), "C compiler required")
class RelocStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mng-reloc-stream-")
        cls.binary = Path(cls.temp.name) / "reloc-stream-case"
        compiler = shutil.which("cc") or shutil.which("clang")
        result = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                 "-I", str(ROOT / "runtime_common"),
                                 str(ROOT / "runtime_common/reloc_stream.c"),
                                 str(ROOT / "tests/reloc_stream_case.c"),
                                 "-o", str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_valid_relr_rela_and_plt_match_expected_records(self):
        self.assert_case("valid")

    def test_source_table_overlapping_writable_data_is_rejected(self):
        self.assert_case("source_overlap")

    def test_unsupported_kind_is_rejected(self):
        self.assert_case("bad_kind")

    def test_symbol_and_target_bounds_are_checked(self):
        self.assert_case("bad_symbol")
        self.assert_case("bad_target")

    def test_relr_bitmap_needs_direct_base(self):
        self.assert_case("bitmap_first")

    def test_callback_can_stop_walk(self):
        self.assert_case("visitor_stop")

    def assert_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
