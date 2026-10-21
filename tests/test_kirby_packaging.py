"""Packaging policy uses game resources, without personal game data."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kirby_package", ROOT / "games/kirby/package_preview.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)

class KirbyPackagingTests(unittest.TestCase):
    def select(self, preferences, env=None):
        with tempfile.TemporaryDirectory(prefix="kirby-language-") as tmp:
            host = Path(tmp)
            index = host / "extracted/v0/romfs/index.json"
            index.parent.mkdir(parents=True)
            import json
            index.write_text(json.dumps({"files": [{"path": f"msg/Eclair/{name}/Cmn.msbt"} for name in
                ("JP_Japanese", "US_English", "EU_English", "EU_French", "US_French", "EU_German", "US_Spanish", "EU_Spanish")]}))
            return package.select_language(host, env=env or {}, preferences=preferences)

    def test_environment_language_falls_back_only_to_available_resources(self):
        self.assertEqual(self.select(["zh-Hans-CN"]), "en-US")
        self.assertEqual(self.select(["ja-JP"]), "ja")
        self.assertEqual(self.select(["fr-CA"]), "fr-CA")
        self.assertEqual(self.select(["en-GB"]), "en-GB")
        self.assertEqual(self.select(["de-DE"]), "de")
        self.assertEqual(self.select(["zh-Hant-TW", "ja-JP"]), "ja")

    def test_explicit_locale_precedes_mac_preferences_and_c_is_ignored(self):
        self.assertEqual(self.select(["ja"], {"LANG": "fr_CA.UTF-8"}), "fr-CA")
        self.assertEqual(self.select(["de"], {"LC_ALL": "C.UTF-8", "LANG": "ja_JP.UTF-8"}), "de")
        self.assertEqual(self.select(["ja"], {"TOTK_LANG": "en-US"}), "en-US")

    def test_launcher_removes_game_interval_wait_and_records_package_language(self):
        source = package.launcher_source("en-US")
        self.assertIn('export DM_PRESENT_INTERVAL="${DM_PRESENT_INTERVAL:-display}"', source)
        self.assertIn('export TOTK_LANG="${TOTK_LANG:-en-US}"', source)
        self.assertNotIn("DM_PRESENT_HZ=30", source)
        self.assertNotIn("TOTK_MFX=interp30", source)
