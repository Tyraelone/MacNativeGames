"""Native mapped image ownership, digest, linkage, and page permissions."""

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "darwin" and (shutil.which("cc") or shutil.which("clang")),
                     "macOS C compiler required")
class ModuleImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mng-module-image-")
        cls.binary = Path(cls.temp.name) / "module-image-case"
        cls.image = Path(cls.temp.name) / "image.bin"
        data = bytearray(0x14000)
        data[0] = 0x5a
        cls.image.write_bytes(data)
        cls.digest = hashlib.sha256(data).hexdigest()
        cls.symlink = Path(cls.temp.name) / "image-link.bin"
        cls.symlink.symlink_to(cls.image)
        compiler = shutil.which("cc") or shutil.which("clang")
        result = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime_common"),
             *[str(ROOT / f"runtime_common/{name}.c") for name in
               ("symbol_view", "reloc_stream", "reloc_apply", "guest_link",
                "module_descriptor", "module_link", "module_image")],
             str(ROOT / "tests/module_image_case.c"), "-o", str(cls.binary)],
            capture_output=True, text=True)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_case(self, name, image=None, digest=None):
        result = subprocess.run([str(self.binary), str(image or self.image),
                                 digest or self.digest, name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")

    def test_map_link_and_seal_permissions(self):
        self.assert_case("success")

    def test_rejects_digest_mismatch(self):
        self.assert_case("hash", digest="0" * 64)

    def test_rejects_size_mismatch(self):
        self.assert_case("size")

    def test_rejects_symlink(self):
        self.assert_case("symlink", image=self.symlink)

    def test_rejects_unaligned_layout_before_permission_changes(self):
        self.assert_case("layout")

    def test_shared_section_pages_remain_never_writable_and_executable(self):
        self.assert_case("sharedpage")

    def test_no_patch_region_seals_as_read_only(self):
        self.assert_case("nopatch")

    def test_rejects_text_and_data_sharing_writable_executable_page(self):
        self.assert_case("wx_overlap")
