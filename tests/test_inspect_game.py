"""Read-only identity and support decisions use contents, never names."""

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers import modes
from test_game_containers import (AREA, CONTENT, HEADER, TITLE, TITLEKEK,
                                  encrypt, game_image, nca, partition)
from test_updates import update_nca
from extract_exefs import decrypt

import inspect_game


ROOT = Path(__file__).resolve().parents[1]
MARIO = "010015100B514000"


def cnmt_nca(title: int, version: int, content_type: int = 0x81) -> bytes:
    """A tiny encrypted Meta NCA with a hashed CNMT PFS0."""
    cnmt = bytearray(0x20)
    struct.pack_into("<QI", cnmt, 0, title, version)
    cnmt[12] = content_type
    pfs = partition([(f"Patch_{title:016x}.cnmt", bytes(cnmt))])
    digest = hashlib.sha256(pfs).digest()
    fs = bytearray(512)
    fs[2:5] = bytes([1, 2, 3])
    fs[8:40] = hashlib.sha256(digest).digest()
    struct.pack_into("<IIQQQQ", fs, 0x28, 4096, 2, 0, 32, 512, len(pfs))
    body = digest.ljust(512, b"\0") + pfs.ljust((len(pfs) + 511) // 512 * 512, b"\0")
    template = nca(title=title, content=1)
    header = bytearray(b"".join(
        decrypt(HEADER, modes.XTS(i.to_bytes(16, "big")),
                template[i * 512:(i + 1) * 512]) for i in range(6)))
    struct.pack_into("<II", header, 0x240, 0xc00 // 512, (0xc00 + len(body)) // 512)
    struct.pack_into("<Q", header, 0x208, 0xc00 + len(body))
    header[0x400:0x600] = fs
    header[0x280:0x2a0] = hashlib.sha256(fs).digest()
    encrypted_header = b"".join(
        encrypt(HEADER, modes.XTS(i.to_bytes(16, "big")), header[i * 512:(i + 1) * 512])
        for i in range(6))
    encrypted_body = encrypt(CONTENT, modes.CTR(bytes(8) + (0xc00 // 16).to_bytes(8, "big")),
                             body)
    return encrypted_header + encrypted_body


def rewrite_meta_header(data: bytes, change) -> bytes:
    header = bytearray(b"".join(
        decrypt(HEADER, modes.XTS(i.to_bytes(16, "big")), data[i * 512:(i + 1) * 512])
        for i in range(6)))
    change(header)
    encrypted_header = b"".join(
        encrypt(HEADER, modes.XTS(i.to_bytes(16, "big")), header[i * 512:(i + 1) * 512])
        for i in range(6))
    return encrypted_header + data[0xc00:]


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

    def test_verified_cnmt_reports_raw_version_and_rejects_modified_bytes(self):
        source = self.folder / "update.nsp"
        metadata = cnmt_nca(TITLE + 0x800, 0x50000)
        source.write_bytes(partition([
            ("program.nca", update_nca(managed=False)),
            ("patch.cnmt.nca", metadata),
        ]))
        result = inspect_game.select_program(source, self.keys)
        self.assertEqual(result["cnmt_version_raw"], 0x50000)
        self.assertEqual(result["cnmt_content_type"], "patch")
        damaged = bytearray(metadata)
        damaged[0xc00 + 512 + 20] ^= 1
        source.write_bytes(partition([
            ("program.nca", update_nca(managed=False)),
            ("patch.cnmt.nca", bytes(damaged)),
        ]))
        with self.assertRaisesRegex(ValueError, "CNMT block hash mismatch"):
            inspect_game.select_program(source, self.keys)

    def test_modified_cnmt_layout_byte_cannot_skip_header_hash_check(self):
        metadata = rewrite_meta_header(
            cnmt_nca(TITLE + 0x800, 0x50000),
            lambda header: header.__setitem__(0x402, header[0x402] ^ 1))
        source = self.folder / "changed-header.nsp"
        source.write_bytes(partition([
            ("program.nca", update_nca(managed=False)),
            ("patch.cnmt.nca", metadata),
        ]))
        with self.assertRaisesRegex(ValueError, "CNMT FS header hash mismatch"):
            inspect_game.select_program(source, self.keys)

    def test_other_hashed_cnmt_layout_is_not_assessed(self):
        def change(header):
            struct.pack_into("<I", header, 0x400 + 0x2c, 3)
            header[0x280:0x2a0] = hashlib.sha256(header[0x400:0x600]).digest()

        metadata = rewrite_meta_header(cnmt_nca(TITLE + 0x800, 0x50000), change)
        source = self.folder / "other-layout.nsp"
        source.write_bytes(partition([
            ("program.nca", update_nca(managed=False)),
            ("patch.cnmt.nca", metadata),
        ]))
        result = inspect_game.select_program(source, self.keys)
        self.assertIsNone(result["cnmt_version_raw"])

    def test_cnmt_hash_table_and_content_type_are_checked(self):
        source = self.folder / "update.nsp"
        metadata = bytearray(cnmt_nca(TITLE + 0x800, 0x50000))
        metadata[0xc00] ^= 1
        source.write_bytes(partition([
            ("program.nca", update_nca(managed=False)),
            ("patch.cnmt.nca", bytes(metadata)),
        ]))
        with self.assertRaisesRegex(ValueError, "CNMT hash-table mismatch"):
            inspect_game.select_program(source, self.keys)
        source.write_bytes(partition([
            ("program.nca", update_nca(managed=False)),
            ("patch.cnmt.nca", cnmt_nca(TITLE + 0x800, 0x50000,
                                          content_type=0x80)),
        ]))
        with self.assertRaisesRegex(ValueError, "CNMT identity does not match"):
            inspect_game.select_program(source, self.keys)

    def test_base_cnmt_version_zero_is_still_verified(self):
        source = self.folder / "base.nsp"
        source.write_bytes(partition([
            ("program.nca", nca()),
            ("application.cnmt.nca", cnmt_nca(TITLE, 0, content_type=0x80)),
        ]))
        identity = inspect_game.select_program(source, self.keys)
        self.assertEqual(identity["cnmt_version_raw"], 0)
        self.assertEqual(identity["cnmt_content_type"], "application")
        report = inspect_game.report_from_artifacts(
            identity, {"files": [{"name": "main", "sha256": "a" * 64}]},
            [{"module": "main", "build_id": "b" * 64,
              "segment_hashes_verified": True}],
            {"modules": {"main": {"group_counts": {}}}})
        self.assertEqual(report["checks"]["cnmt_hash_chain"], "pass")

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

    def test_profiles_are_discovered_from_registered_game_directories(self):
        title = "0100000000001000"
        hashes = {"main": "a" * 64, "main.npdm": "b" * 64}
        with tempfile.TemporaryDirectory(prefix="mng-profile-test-") as folder:
            root = Path(folder)
            assets = root / "games/sample/assets"
            assets.mkdir(parents=True)
            (assets / "expected-v1.json").write_text(json.dumps({
                "title_id": title, "display_version": "1.0", "exefs_sha256": hashes}))
            targets = {"sample": (title, "prepared host packaging", root / "builder.py", assets)}
            with patch.object(inspect_game, "TARGETS", targets):
                self.assertEqual(inspect_game.match_profile(title, hashes),
                                 {"target": "sample", "version": "1.0"})
                changed = {**hashes, "main.npdm": "c" * 64}
                self.assertEqual(inspect_game.match_code_profile(title, changed), {
                    "target": "sample", "version": "1.0",
                    "mismatched_files": ["main.npdm"]})

    def test_misfiled_profile_does_not_claim_another_game(self):
        with tempfile.TemporaryDirectory(prefix="mng-profile-test-") as folder:
            root = Path(folder)
            assets = root / "games/sample/assets"
            assets.mkdir(parents=True)
            (assets / "expected-v1.json").write_text(json.dumps({
                "title_id": "0100000000002000", "display_version": "1.0",
                "exefs_sha256": {"main": "a" * 64}}))
            targets = {"sample": ("0100000000001000", "test", root / "builder.py", assets)}
            with patch.object(inspect_game, "TARGETS", targets):
                with self.assertRaisesRegex(ValueError, "Profile title ID mismatch"):
                    inspect_game.match_profile("0100000000001000", {"main": "a" * 64})

    def test_incomplete_registered_profile_fails_cleanly(self):
        with tempfile.TemporaryDirectory(prefix="mng-profile-test-") as folder:
            root = Path(folder)
            assets = root / "games/sample/assets"
            assets.mkdir(parents=True)
            (assets / "expected-v1.json").write_text(json.dumps({
                "title_id": "0100000000001000", "display_version": "1.0"}))
            targets = {"sample": ("0100000000001000", "test", root / "builder.py", assets)}
            with patch.object(inspect_game, "TARGETS", targets):
                with self.assertRaisesRegex(ValueError, "Invalid ExeFS profile"):
                    inspect_game.match_profile("0100000000001000", {"main": "a" * 64})

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
