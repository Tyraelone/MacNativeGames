"""Guest symbol resolution matches the current loader's fallback order."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc") or shutil.which("clang"), "C compiler required")
class GuestLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mng-guest-link-")
        cls.binary = Path(cls.temp.name) / "guest-link-case"
        compiler = shutil.which("cc") or shutil.which("clang")
        result = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                 "-I", str(ROOT / "runtime_common"),
                                 str(ROOT / "runtime_common/symbol_view.c"),
                                 str(ROOT / "runtime_common/guest_link.c"),
                                 str(ROOT / "tests/guest_link_case.c"),
                                 "-o", str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_local_cross_module_preemptible_weak_and_zero(self):
        self.assert_case("guest")

    def test_host_precedes_guest_and_can_fail(self):
        self.assert_case("host")

    def test_missing_strong_and_invalid_first_definition(self):
        self.assert_case("missing")

    def test_invalid_local_and_address_overflow_fail(self):
        self.assert_case("bounds")

    def assert_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
