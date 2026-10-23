"""Exercise direct relocation writes without a game image or host services."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc") or shutil.which("clang"), "C compiler required")
class RelocApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mng-reloc-apply-")
        cls.binary = Path(cls.temp.name) / "reloc-apply-case"
        compiler = shutil.which("cc") or shutil.which("clang")
        result = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                 "-I", str(ROOT / "runtime_common"),
                                 str(ROOT / "runtime_common/reloc_stream.c"),
                                 str(ROOT / "runtime_common/reloc_apply.c"),
                                 str(ROOT / "tests/reloc_apply_case.c"),
                                 "-o", str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_writes_relative_and_symbolic_values(self):
        self.assert_case("valid")

    def test_rejects_writable_source_before_any_write(self):
        self.assert_case("source_overlap")

    def test_resolution_failure_leaves_failed_and_later_targets_untouched(self):
        self.assert_case("resolve_failure")


if __name__ == "__main__":
    unittest.main()
