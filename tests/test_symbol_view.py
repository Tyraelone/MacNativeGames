"""The C symbol view preserves the current loader's lookup behavior."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc") or shutil.which("clang"), "C compiler required")
class SymbolViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mng-symbol-view-")
        cls.binary = Path(cls.temp.name) / "symbol-view-case"
        compiler = shutil.which("cc") or shutil.which("clang")
        result = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                 "-I", str(ROOT / "runtime_common"),
                                 str(ROOT / "runtime_common/symbol_view.c"),
                                 str(ROOT / "tests/symbol_view_case.c"),
                                 "-o", str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_first_definition_and_reserved_index_match_loader(self):
        self.assert_case("valid")

    def test_source_tables_must_precede_writable_data(self):
        self.assert_case("str_overlap")
        self.assert_case("sym_overlap")

    def test_bad_names_are_rejected_before_indexing(self):
        self.assert_case("bad_offset")
        self.assert_case("unterminated")

    def test_index_workspace_capacity_is_checked(self):
        self.assert_case("short_index")

    def assert_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
