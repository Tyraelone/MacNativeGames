import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "games/mario_wonder/build_app.py"
spec = importlib.util.spec_from_file_location("mario_build_app", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class MarioPackagePathTests(unittest.TestCase):
    def test_generated_paths_must_stay_outside_repository(self):
        for path in (builder.REPO, builder.REPO / "build", SCRIPT.parent / "Preview.app"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                builder.external(path)

    def test_external_work_and_app_paths_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Mario Wonder.app"
            self.assertEqual(builder.external(path), path.resolve())

    def test_packaging_rejects_a_non_mario_native_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "native"
            binary.write_bytes(b"native host for a different title")
            with self.assertRaises(ValueError):
                builder.verify_native_variant(binary)


if __name__ == "__main__":
    unittest.main()
