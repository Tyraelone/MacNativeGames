"""Module inventory must follow the verified ExeFS contents."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "games/totk/scripts"
sys.path.insert(0, str(SCRIPTS))
import prepare_modules  # noqa: E402


class ModuleInventoryTests(unittest.TestCase):
    def test_module_discovery_accepts_games_without_subsdk(self):
        with tempfile.TemporaryDirectory(prefix="mng-modules-") as folder:
            exefs = Path(folder)
            for name in ("sdk", "main", "rtld"):
                (exefs / name).write_bytes(b"NSO0" + bytes(252))
            (exefs / "main.npdm").write_bytes(b"META" + bytes(64))
            self.assertEqual(prepare_modules.discover_nso_modules(exefs), ["rtld", "main", "sdk"])

    def test_module_discovery_keeps_existing_subsdk_modules(self):
        with tempfile.TemporaryDirectory(prefix="mng-modules-") as folder:
            exefs = Path(folder)
            for name in ("subsdk1", "sdk", "subsdk0", "main", "rtld"):
                (exefs / name).write_bytes(b"NSO0" + bytes(252))
            self.assertEqual(
                prepare_modules.discover_nso_modules(exefs),
                ["rtld", "main", "sdk", "subsdk0", "subsdk1"],
            )

    def test_dependency_map_uses_the_recorded_module_set(self):
        with tempfile.TemporaryDirectory(prefix="mng-dependencies-") as folder:
            directory = Path(folder)
            (directory / "modules.json").write_text(json.dumps([
                {"module": "rtld"}, {"module": "main"}, {"module": "sdk"}
            ]))
            for name in ("rtld", "main", "sdk"):
                (directory / f"{name}-inventory.json").write_text(json.dumps({
                    "needed": [],
                    "imports": [{"name": "test_symbol"}] if name == "main" else [],
                    "exports": [{"name": "test_symbol", "value": 4,
                                 "binding": 1, "type": 2}] if name == "sdk" else [],
                }))
            output = directory / "map.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "map_dependencies.py"), str(directory),
                 "--output", str(output)], capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(set(report["modules"]), {"rtld", "main", "sdk"})
            self.assertEqual(report["modules"]["main"]["resolved_by_name"], 1)


if __name__ == "__main__":
    unittest.main()
