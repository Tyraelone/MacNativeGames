import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "games/mario_wonder/launcher.m"
SDK = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk"


@unittest.skipUnless(sys.platform == "darwin" and Path(SDK).exists(), "needs macOS Xcode 26.5 SDK")
class MarioLauncherIsolationTests(unittest.TestCase):
    def test_inherited_totk_paths_cannot_redirect_mario_bundle_or_saves(self):
        tests = Path.home() / "Library/Application Support/MacNativeGames/MarioWonder/tests"
        tests.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="launcher-", dir=tests) as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            app = root / "MarioProbe.app"
            macos = app / "Contents/MacOS"
            game = app / "Contents/Resources/game"
            (game / "build").mkdir(parents=True)
            macos.mkdir()
            with (app / "Contents/Info.plist").open("wb") as file:
                plistlib.dump({"CFBundleExecutable": "MarioWonder", "CFBundlePackageType": "APPL",
                               "CFBundleIdentifier": "local.macnativegames.mario-probe"}, file)
            native = game / "build/mario-wonder-native"
            native.write_text('#!/bin/sh\n/usr/bin/env > "$MARIO_ENV_PROBE"\n')
            native.chmod(0o755)
            env = os.environ.copy()
            env["SDKROOT"] = SDK
            env["CFFIXED_USER_HOME"] = str(home)
            subprocess.run(["xcrun", "clang", "-fobjc-arc", str(SOURCE),
                            "-framework", "AppKit", "-o", str(macos / "MarioWonder")],
                           env=env, check=True, stdout=subprocess.DEVNULL)
            probe = root / "environment.txt"
            env["MARIO_ENV_PROBE"] = str(probe)
            poison = root / "totk-user-data"
            for name in ("TOTK_PROFILE_DIR", "TOTK_GAME_SLOT_DIR", "TOTK_SHADER_CACHE",
                         "TOTK_ROMFS_PROOF_DIR", "TOTK_ROMFS", "TOTK_SHARED_FONTS",
                         "TOTK_PROFILE_IMAGE", "TOTK_INPUT_FILE"):
                env[name] = str(poison / name)
            subprocess.run([str(macos / "MarioWonder")], env=env, check=True, timeout=10)
            actual = dict(line.split("=", 1) for line in probe.read_text().splitlines() if "=" in line)
            for name in ("TOTK_PROFILE_DIR", "TOTK_GAME_SLOT_DIR", "TOTK_SHADER_CACHE",
                         "TOTK_ROMFS_PROOF_DIR", "TOTK_ROMFS", "TOTK_SHARED_FONTS", "TOTK_PROFILE_IMAGE"):
                with self.subTest(name=name):
                    self.assertNotEqual(actual[name], env[name])
            self.assertTrue(actual["TOTK_PROFILE_DIR"].endswith("/MacNativeGames/MarioWonder/profile"))
            self.assertEqual(actual["TOTK_ROMFS"], str(game / "romfs"))
            self.assertNotIn("TOTK_INPUT_FILE", actual)


if __name__ == "__main__":
    unittest.main()
