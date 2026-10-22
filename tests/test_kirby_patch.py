"""The preview adaptation must apply to the exact host revision it documents."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST_BASE = "f5cc1519c5c6aed8b21c20317a9cee15f3f6d746"


class KirbyPatchTests(unittest.TestCase):
    def test_preview_patch_applies_to_pinned_host(self):
        with tempfile.TemporaryDirectory(prefix="kirby-host-source-") as temporary:
            archive = subprocess.check_output(
                ["git", "archive", HOST_BASE, "games/totk"], cwd=ROOT)
            subprocess.run(["tar", "-x", "-C", temporary, "--strip-components=2"],
                           input=archive, check=True)
            subprocess.run(["git", "apply", "--check", "-p1",
                            str(ROOT / "games/kirby/native-preview.patch")],
                           cwd=temporary, check=True)


if __name__ == "__main__":
    unittest.main()
