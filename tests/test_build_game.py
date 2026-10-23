"""The shared command must preserve each game's existing build contract."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_game


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "build_game.py"


class BuildGameCliTests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(ENTRY), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_list_distinguishes_full_build_from_prepared_host_packaging(self):
        result = self.command("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("totk", result.stdout)
        self.assertIn("XCI/NSP", result.stdout)
        self.assertIn("kirby-preview", result.stdout)
        self.assertIn("prepared host", result.stdout)
        self.assertIn("castlevania", result.stdout)
        self.assertIn("verified work", result.stdout)

    def test_top_level_help_explains_known_targets(self):
        result = self.command("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("totk", result.stdout)
        self.assertIn("kirby-preview", result.stdout)
        self.assertIn("castlevania", result.stdout)
        self.assertIn("Unknown games", result.stdout)

    def test_unknown_target_stops_without_running_a_builder(self):
        result = self.command("unknown-game", "--out", "/tmp/would-be.app")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown-game", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_target_help_comes_from_its_existing_builder(self):
        cases = (
            ("totk", "--firmware"),
            ("kirby-preview", "--host"),
            ("castlevania", "--shader-seed"),
        )
        for target, distinct_option in cases:
            with self.subTest(target=target):
                result = self.command(target, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(distinct_option, result.stdout)


class BuildGameDispatchTests(unittest.TestCase):
    def test_each_target_routes_to_its_existing_builder_without_rewriting_args(self):
        self.assertTrue(hasattr(build_game, "command_for"), "command_for is missing")
        for target, relative_script in (
            ("totk", "build_app.py"),
            ("kirby-preview", "games/kirby/package_preview.py"),
            ("castlevania", "games/castlevania/build_app.py"),
        ):
            with self.subTest(target=target):
                arguments = ["--out", "/tmp/name with spaces.app", "literal$(touch /tmp/nope)"]
                self.assertEqual(
                    build_game.command_for(target, arguments),
                    [sys.executable, str(ROOT / relative_script), *arguments],
                )

    def test_builder_exit_code_is_returned_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="mng-build-dispatch-") as folder:
            script = Path(folder) / "exit.py"
            script.write_text("import sys\nsys.exit(17 if sys.argv[1:] == ['--help'] else 19)\n")
            with patch.dict(build_game.TARGETS, {
                "castlevania": ("test", "test", script),
            }):
                self.assertEqual(build_game.main(["castlevania", "--help"]), 17)

    def test_signaled_builder_returns_conventional_shell_status(self):
        with tempfile.TemporaryDirectory(prefix="mng-build-signal-") as folder:
            script = Path(folder) / "terminate_child.py"
            script.write_text(
                "import os, signal\n"
                "os.kill(os.getpid(), signal.SIGTERM)\n"
            )
            with patch.dict(build_game.TARGETS, {
                "castlevania": ("test", "test", script),
            }):
                self.assertEqual(build_game.main(["castlevania"]), 143)


if __name__ == "__main__":
    unittest.main()
