"""Shared input tools and legacy TOTK entry points have one implementation."""

import subprocess
import sys
import tempfile
import unittest
import shutil
from pathlib import Path
from unittest import mock

from test_game_containers import AREA, HEADER, TITLEKEK, game_image, romfs
import build_app


ROOT = Path(__file__).resolve().parents[1]


class SharedGameToolsTests(unittest.TestCase):
    def test_legacy_entry_points_export_shared_functions(self):
        from game_tools import extract_exefs, map_dependencies, prepare_modules
        import extract_exefs as legacy_exefs
        import map_dependencies as legacy_dependencies
        import prepare_modules as legacy_modules

        self.assertIs(legacy_exefs.container_entries, extract_exefs.container_entries)
        self.assertIs(legacy_modules.discover_nso_modules,
                      prepare_modules.discover_nso_modules)
        self.assertIs(legacy_dependencies.main, map_dependencies.main)

    def test_shared_exefs_command_reads_synthetic_nsp(self):
        with tempfile.TemporaryDirectory(prefix="mng-shared-tools-") as folder:
            root = Path(folder)
            source = root / "base.nsp"
            source.write_bytes(game_image("nsp"))
            keys = root / "prod.keys"
            keys.write_text("\n".join(f"{name} = {value.hex()}" for name, value in (
                ("header_key", HEADER), ("key_area_key_application_00", AREA),
                ("titlekek_00", TITLEKEK))))
            output = root / "exefs"
            result = subprocess.run(
                [sys.executable, str(ROOT / "game_tools/extract_exefs.py"),
                 str(source), "--keys", str(keys), "--output", str(output)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / "main").read_bytes(), b"synthetic main")

    def test_shared_romfs_command_verifies_synthetic_nsp(self):
        with tempfile.TemporaryDirectory(prefix="mng-shared-romfs-") as folder:
            root = Path(folder)
            source = root / "base.nsp"
            source.write_bytes(game_image("nsp"))
            keys = root / "prod.keys"
            keys.write_text("\n".join(f"{name} = {value.hex()}" for name, value in (
                ("header_key", HEADER), ("key_area_key_application_00", AREA),
                ("titlekek_00", TITLEKEK))))
            exefs = root / "exefs"
            extracted = subprocess.run(
                [sys.executable, str(ROOT / "game_tools/extract_exefs.py"),
                 str(source), "--keys", str(keys), "--output", str(exefs)],
                capture_output=True, text=True, check=False)
            self.assertEqual(extracted.returncode, 0, extracted.stderr)
            output = root / "romfs"
            result = subprocess.run(
                [sys.executable, str(ROOT / "game_tools/extract_romfs.py"),
                 "--keys", str(keys), "--manifest", str(root / "extraction-manifest.json"),
                 "--output", str(output)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / "romfs.bin").read_bytes(), romfs())
            self.assertTrue((output / "index.json").is_file())

    def test_shared_update_command_requires_title_id(self):
        command = [sys.executable, str(ROOT / "game_tools/extract_update_romfs.py"),
                   "base.nsp", "update.nsp", "--keys", "keys.txt", "--hactool", "hactool",
                   "--output", "merged"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--title-id", result.stderr)

    @unittest.skipUnless(shutil.which("rsync"), "rsync needed for real work copy")
    def test_copied_totk_entry_points_find_shared_tools(self):
        with tempfile.TemporaryDirectory(prefix="mng-shared-work-") as folder:
            root = Path(folder)
            source = root / "source"
            scripts = source / "scripts"
            scripts.mkdir(parents=True)
            (source / "requirements.txt").write_text("")
            for name in ("extract_exefs", "extract_romfs", "extract_update_romfs",
                         "prepare_modules", "map_dependencies"):
                shutil.copy2(ROOT / f"games/totk/scripts/{name}.py", scripts / f"{name}.py")

            def copy_only(command, *_args, **_kwargs):
                if str(command[0]) == "rsync":
                    subprocess.run([str(part) for part in command], check=True, capture_output=True)

            work = root / "work"
            with mock.patch.object(build_app, "GAME", source), \
                 mock.patch.object(build_app, "run", side_effect=copy_only), \
                 mock.patch.object(build_app, "git_fetch"):
                tree = build_app.prepare_work(work, Path(sys.executable), work / "logs")

            self.assertTrue((work / "game_tools/extract_exefs.py").is_file())
            self.assertTrue((work / "game_tools/extract_update_romfs.py").is_file())
            for name in ("extract_exefs", "extract_romfs", "extract_update_romfs",
                         "prepare_modules", "map_dependencies"):
                result = subprocess.run(
                    [sys.executable, str(tree / f"scripts/{name}.py"), "--help"],
                    cwd=tree, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
