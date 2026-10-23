"""Gate return lookup uses prepared immutable module ranges and sorted rows."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc") or shutil.which("clang"), "C compiler required")
class ModuleGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mng-module-gate-")
        cls.binary = Path(cls.temp.name) / "module-gate-case"
        compiler = shutil.which("cc") or shutil.which("clang")
        result = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime_common"),
             str(ROOT / "runtime_common/module_gate.c"),
             str(ROOT / "tests/module_gate_case.c"), "-o", str(cls.binary)],
            capture_output=True, text=True)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")

    def test_exact_return_lookup_keeps_original_module_order(self):
        self.assert_case("lookup")

    def test_invalid_or_overlapping_ranges_do_not_build_a_table(self):
        self.assert_case("invalid")
