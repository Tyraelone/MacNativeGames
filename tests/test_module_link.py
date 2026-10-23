"""Compact descriptors drive the common guest linker with caller-owned workspace."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc") or shutil.which("clang"), "C compiler required")
class ModuleLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mng-module-link-")
        cls.binary = Path(cls.temp.name) / "module-link-case"
        compiler = shutil.which("cc") or shutil.which("clang")
        result = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime_common"),
             *[str(ROOT / f"runtime_common/{name}.c") for name in
               ("symbol_view", "reloc_stream", "reloc_apply", "guest_link",
                "module_descriptor", "module_link")],
             str(ROOT / "tests/module_link_case.c"), "-o", str(cls.binary)],
            capture_output=True, text=True)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_descriptor_drives_guest_host_weak_and_relative_links(self):
        self.assert_case("success")

    def test_short_workspace_and_invalid_source_table_are_rejected(self):
        self.assert_case("invalid")

    def test_unprepared_module_prevents_any_writes(self):
        self.assert_case("unprepared")

    def test_host_failure_reports_partial_writes(self):
        self.assert_case("host_error")
