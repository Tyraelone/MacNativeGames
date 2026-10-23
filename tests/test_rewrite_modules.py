"""The shared rewrite probe handles actual NSO sets without game data."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from game_tools import rewrite_modules


ROOT = Path(__file__).resolve().parents[1]


class RewriteModulesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mng-rewrite-modules-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.exefs = self.work / "exefs"
        self.exefs.mkdir()
        self.manifest = self.work / "extraction-manifest.json"
        self.output = self.work / "rewritten"
        rows = []
        for name in ("rtld", "main", "sdk"):
            data = b"NSO0" + bytes(0x3c) + bytes.fromhex("ab" * 16) + bytes(32)
            (self.exefs / name).write_bytes(data)
            rows.append({"name": name, "size": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})
        rows.append({"name": "main.npdm", "size": 4, "sha256": "0" * 64})
        self.manifest.write_text(json.dumps({"title_id": "010015100B514000", "files": rows}))

    def fake_rewrite(self, command, **kwargs):
        name = command[-1]
        destination = Path(command[-2])
        destination.mkdir()
        (destination / f"{name}.patched.bin").write_bytes(b"rewritten:" + name.encode())
        (destination / f"{name}.fixups.tsv").write_text("# PATCH_OFF\t0x10000\n")
        (destination / f"{name}.gates.tsv").write_text("0x10\tsvc\t1\t0x0\n")
        for suffix in ("cuts", "params", "obs"):
            (destination / f"{name}.{suffix}.tsv").write_text("# BUILD_ID\t" + "ab" * 16 + "\n")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    def test_discovers_three_modules_and_publishes_verified_external_output(self):
        with patch.object(rewrite_modules.subprocess, "run", side_effect=self.fake_rewrite) as worker:
            report = rewrite_modules.rewrite_exefs(self.exefs, self.manifest, self.output)
        self.assertEqual([call.args[0][-1] for call in worker.call_args_list],
                         ["rtld", "main", "sdk"])
        self.assertEqual(set(report["modules"]), {"rtld", "main", "sdk"})
        self.assertEqual(report["runtime"], "not_assessed")
        self.assertEqual(report["modules"]["main"]["gates"], 1)
        self.assertEqual(report["modules"]["main"]["cuts"], 0)
        self.assertTrue((self.output / "rewrite-summary.json").is_file())
        self.assertTrue((self.output / "main/main.patched.bin").is_file())

    def test_hash_mismatch_stops_before_any_rewrite(self):
        path = self.exefs / "main"
        data = path.read_bytes()
        path.write_bytes(data[:-1] + b"\x01")
        with patch.object(rewrite_modules.subprocess, "run") as worker:
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                rewrite_modules.rewrite_exefs(self.exefs, self.manifest, self.output)
        worker.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_generated_output_inside_source_project_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the source project"):
            rewrite_modules.rewrite_exefs(self.exefs, self.manifest, ROOT / "test-rewrite-output")
        self.assertFalse((ROOT / "test-rewrite-output").exists())

    def test_output_symlink_is_rejected_without_touching_its_target(self):
        target = self.work / "real-output"
        self.output.symlink_to(target, target_is_directory=True)
        with patch.object(rewrite_modules.subprocess, "run") as worker:
            with self.assertRaisesRegex(ValueError, "symlink"):
                rewrite_modules.rewrite_exefs(self.exefs, self.manifest, self.output)
        worker.assert_not_called()
        self.assertFalse(target.exists())

    def test_game_specific_patch_record_is_rejected_and_staging_removed(self):
        def patched(command, **kwargs):
            result = self.fake_rewrite(command, **kwargs)
            name = command[-1]
            if name == "main":
                with (Path(command[-2]) / "main.cuts.tsv").open("a") as stream:
                    stream.write("0x20\t00000000\t00000000\tall\tgame patch\n")
            return result
        with patch.object(rewrite_modules.subprocess, "run", side_effect=patched):
            with self.assertRaisesRegex(ValueError, "game-specific"):
                rewrite_modules.rewrite_exefs(self.exefs, self.manifest, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(path.name for path in self.work.iterdir()),
                         ["exefs", "extraction-manifest.json"])

    def test_second_module_failure_discards_unpublished_rewrites(self):
        def fail_second(command, **kwargs):
            if command[-1] == "main":
                return subprocess.CompletedProcess(command, 7, "", "unsupported instruction")
            return self.fake_rewrite(command, **kwargs)

        with patch.object(rewrite_modules.subprocess, "run", side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, "unsupported instruction"):
                rewrite_modules.rewrite_exefs(self.exefs, self.manifest, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(path.name for path in self.work.iterdir()),
                         ["exefs", "extraction-manifest.json"])


if __name__ == "__main__":
    unittest.main()
