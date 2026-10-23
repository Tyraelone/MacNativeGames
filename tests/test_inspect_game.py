"""Read-only identity and support decisions use contents, never names."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_game_containers import (AREA, HEADER, TITLE, TITLEKEK, game_image,
                                  nca, partition)
from test_updates import update_nca

import inspect_game


ROOT = Path(__file__).resolve().parents[1]
MARIO = "010015100B514000"


class InspectIdentityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mng-inspect-test-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.keys = self.folder / "prod.keys"
        self.keys.write_text("\n".join(f"{name} = {value.hex()}" for name, value in (
            ("header_key", HEADER), ("key_area_key_application_00", AREA),
            ("titlekek_00", TITLEKEK),
        )))

    def test_base_identity_comes_from_nca_not_filename(self):
        source = self.folder / "wrong-update-v9.nsp"
        source.write_bytes(game_image("nsp"))
        result = inspect_game.select_program(source, self.keys)
        self.assertEqual(result["title_id"], f"{TITLE:016X}")
        self.assertEqual(result["package_kind"], "base")
        self.assertEqual(result["container"], "nsp")

    def test_update_uses_bktr_and_patch_metadata_identity(self):
        source = self.folder / "wrong-base-v0.nsp"
        source.write_bytes(partition([
            ("program.nca", update_nca(managed=False)),
            ("patch.cnmt.nca", nca(title=TITLE + 0x800, content=1)),
        ]))
        result = inspect_game.select_program(source, self.keys)
        self.assertEqual(result["title_id"], f"{TITLE:016X}")
        self.assertEqual(result["package_kind"], "update")
        self.assertEqual(result["metadata_title_ids"], [f"{TITLE + 0x800:016X}"])

    def test_combined_package_requires_explicit_title_selection(self):
        other = 0x0100BA4026E94000
        secure = partition([
            ("first.nca", nca()),
            ("second.nca", nca(title=other)),
        ], hfs=True)
        header = bytearray(0x200)
        header[0x100:0x104] = b"HEAD"
        import struct
        struct.pack_into("<Q", header, 0x130, 0x200)
        source = self.folder / "combined.xci"
        source.write_bytes(header + partition([("secure", secure)], hfs=True))
        with self.assertRaisesRegex(ValueError, "--title-id"):
            inspect_game.select_program(source, self.keys)
        selected = inspect_game.select_program(source, self.keys, f"{other:016X}")
        self.assertEqual(selected["title_id"], f"{other:016X}")

    def test_combined_xci_update_has_explicit_unsupported_error(self):
        secure = partition([
            ("base.nca", nca()),
            ("update.nca", update_nca(managed=False)),
        ], hfs=True)
        header = bytearray(0x200)
        header[0x100:0x104] = b"HEAD"
        import struct
        struct.pack_into("<Q", header, 0x130, 0x200)
        source = self.folder / "combined-update.xci"
        source.write_bytes(header + partition([("secure", secure)], hfs=True))
        with self.assertRaisesRegex(ValueError, "Combined update XCI is unsupported"):
            inspect_game.select_program(source, self.keys, f"{TITLE:016X}")

    def test_profile_match_requires_every_exefs_hash(self):
        profile = json.loads((ROOT / "games/totk/assets/expected-v1.0.0.json").read_text())
        hashes = profile["exefs_sha256"].copy()
        result = inspect_game.match_profile(profile["title_id"], hashes)
        self.assertEqual(result, {"target": "totk", "version": "1.0.0"})
        hashes["sdk"] = "0" * 64
        self.assertIsNone(inspect_game.match_profile(profile["title_id"], hashes))
        self.assertIsNone(inspect_game.match_profile("010015100B514000", profile["exefs_sha256"]))

    def test_report_separates_known_code_from_unknown_title_and_capabilities(self):
        profile = json.loads((ROOT / "games/totk/assets/expected-v1.0.0.json").read_text())
        files = [{"name": name, "sha256": digest} for name, digest
                 in profile["exefs_sha256"].items()]
        modules = [{"module": "main", "build_id": "a" * 64,
                    "segment_hashes_verified": True}]
        dependencies = {"modules": {"main": {"group_counts": {"nn::audio": 7}}}}
        identity = {"title_id": profile["title_id"], "container": "nsp",
                    "package_kind": "base", "metadata_title_ids": [profile["title_id"]]}
        known = inspect_game.report_from_artifacts(identity, {"files": files},
                                                   modules, dependencies)
        self.assertEqual(known["status"], "verified_exefs_profile")
        self.assertEqual(known["profile"], {"target": "totk", "version": "1.0.0"})
        self.assertEqual(known["checks"]["exefs_hash_chain"], "pass")
        self.assertEqual(known["checks"]["nca_rsa_signatures"], "not_checked")
        self.assertEqual(known["checks"]["host_services"], "not_assessed")
        self.assertEqual(known["main_import_groups"], {"nn::audio": 7})
        without_nso_hashes = inspect_game.report_from_artifacts(
            identity, {"files": files}, [{**modules[0], "segment_hashes_verified": False}],
            dependencies)
        self.assertEqual(without_nso_hashes["checks"]["nso_segment_hashes"], "not_present")
        mixed_nso_hashes = inspect_game.report_from_artifacts(
            identity, {"files": files}, modules + [
                {"module": "sdk", "build_id": "b" * 64,
                 "segment_hashes_verified": False}], dependencies)
        self.assertEqual(mixed_nso_hashes["checks"]["nso_segment_hashes"], "partial")
        self.assertEqual(mixed_nso_hashes["modules"][1]["segment_hashes_verified"], False)
        files[0] = {**files[0], "sha256": "0" * 64}
        unknown_version = inspect_game.report_from_artifacts(identity, {"files": files},
                                                             modules, dependencies)
        self.assertEqual(unknown_version["status"], "known_title_unknown_version")
        self.assertIsNone(unknown_version["code_match"])
        metadata_variant = [{"name": name, "sha256": "0" * 64 if name == "main.npdm" else digest}
                            for name, digest in profile["exefs_sha256"].items()]
        partial = inspect_game.report_from_artifacts(identity, {"files": metadata_variant},
                                                     modules, dependencies)
        self.assertEqual(partial["status"], "known_title_unknown_version")
        self.assertEqual(partial["code_match"], {
            "target": "totk", "version": "1.0.0", "mismatched_files": ["main.npdm"]
        })
        unported = inspect_game.report_from_artifacts(
            {**identity, "title_id": MARIO}, {"files": files}, modules, dependencies)
        self.assertEqual(unported["status"], "unported_title")
        self.assertIsNone(unported["profile"])

    def test_inspect_cleans_external_temporary_outputs(self):
        source = self.folder / "base.nsp"
        source.write_bytes(game_image("nsp"))
        profile = json.loads((ROOT / "games/totk/assets/expected-v1.0.0.json").read_text())
        outputs = []

        def fake_run(command, **kwargs):
            self.assertTrue(kwargs["check"])
            name = Path(command[1]).name
            output = Path(command[command.index("--output") + 1])
            self.assertFalse(output.resolve().is_relative_to(ROOT))
            outputs.append(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            if name == "extract_exefs.py":
                output.mkdir()
                (output.parent / "extraction-manifest.json").write_text(json.dumps({
                    "files": [{"name": key, "sha256": value} for key, value
                              in profile["exefs_sha256"].items()]
                }))
            elif name == "prepare_modules.py":
                output.mkdir()
                (output / "modules.json").write_text(json.dumps([
                    {"module": "main", "build_id": "a" * 64,
                     "segment_hashes_verified": True}
                ]))
            else:
                output.write_text(json.dumps({"modules": {"main": {"group_counts": {}}}}))
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory(prefix="mng-inspect-parent-") as parent:
            with patch.object(inspect_game.subprocess, "run", side_effect=fake_run):
                result = inspect_game.inspect(source, self.keys, temp_root=Path(parent))
            self.assertEqual(result["status"], "verified_exefs_profile")
            self.assertEqual(len(outputs), 3)
            self.assertEqual(list(Path(parent).iterdir()), [])

    def test_failed_child_cleans_temporary_outputs_and_emits_no_success_json(self):
        source = self.folder / "base.nsp"
        source.write_bytes(game_image("nsp"))
        with tempfile.TemporaryDirectory(prefix="mng-inspect-parent-") as parent:
            failure = subprocess.CalledProcessError(1, ["extract_exefs.py"],
                                                    stderr="hash-table mismatch")
            with patch.object(inspect_game.subprocess, "run", side_effect=failure):
                with self.assertRaisesRegex(ValueError, "hash-table mismatch"):
                    inspect_game.inspect(source, self.keys, temp_root=Path(parent))
            self.assertEqual(list(Path(parent).iterdir()), [])

        result = subprocess.run(
            [sys.executable, str(ROOT / "inspect_game.py"), str(source),
             "--keys", str(self.folder / "missing.keys")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Inspect failed", result.stderr)

    def test_temp_root_inside_source_is_rejected(self):
        source = self.folder / "base.nsp"
        source.write_bytes(game_image("nsp"))
        with self.assertRaisesRegex(ValueError, "outside the source checkout"):
            inspect_game.inspect(source, self.keys, temp_root=ROOT)


if __name__ == "__main__":
    unittest.main()
