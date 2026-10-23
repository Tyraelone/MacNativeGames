"""Static runtime table data can be prepared without a game-specific module list."""

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from game_tools import runtime_preflight


ROOT = Path(__file__).resolve().parents[1]


class RuntimePreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mng-runtime-preflight-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.exefs = self.work / "exefs"
        self.exefs.mkdir()
        self.rewrites = self.work / "rewritten"
        self.rewrites.mkdir()
        self.output = self.work / "preflight"
        self.manifest = self.work / "extraction-manifest.json"
        self.title_id = "010015100B514000"
        self.rows = []
        self.rewrite_rows = {}
        for name in ("rtld", "main", "sdk"):
            self.add_module(name)
        self.write_reports()

    def add_module(self, name):
        raw = bytearray(0x100)
        raw[:4] = b"NSO0"
        raw[0x40:0x60] = bytes.fromhex("ab" * 32)
        struct.pack_into("<IIII", raw, 0x90, 0, 0, 0x300, 48)
        source = self.exefs / name
        source.write_bytes(raw)
        self.rows.append({"name": name, "size": len(raw),
                          "sha256": hashlib.sha256(raw).hexdigest()})
        image = bytearray(0x9000)
        struct.pack_into("<I", image, 4, 0x3000)
        image[0x3000:0x3004] = b"MOD0"
        struct.pack_into("<i", image, 0x3004, 0x100)
        tags = [(4, 0x2400), (5, 0x2200), (6, 0x2300), (10, 16), (11, 24),
                (7, 0x3200), (8, 24), (9, 24), (20, 7), (23, 0x3300), (2, 0), (0, 0)]
        for index, pair in enumerate(tags):
            struct.pack_into("<qQ", image, 0x3100 + index * 16, *pair)
        image[0x2200:0x2205] = b"\0foo\0"
        struct.pack_into("<II", image, 0x2400, 1, 2)
        struct.pack_into("<IBBHQQ", image, 0x2300 + 24, 1, 0x12, 0, 0, 0, 0)
        struct.pack_into("<QQq", image, 0x3200, 0x3400, (1 << 32) | 1026, 0)
        folder = self.rewrites / name
        folder.mkdir()
        patched = folder / f"{name}.patched.bin"
        patched.write_bytes(image)
        (folder / f"{name}.fixups.tsv").write_text(
            "# PATCH_OFF\t0x8000\n# KEY_PAGE_OFF\t0x4000\n"
            "# KEY_PAGE_SIZE\t0x4000\n# TEXT_END\t0x1000\n"
            "# RO_OFF\t0x2000\n# DATA_OFF\t0x3000\n")
        (folder / f"{name}.gates.tsv").write_text("0x8100\tsvc\t1\t0x100\n")
        self.rewrite_rows[name] = {
            "nso_sha256": self.rows[-1]["sha256"],
            "patched_sha256": hashlib.sha256(image).hexdigest(),
            "build_id": "ab" * 32, "gates": 1, "cuts": 0, "params": 0, "obs": 0,
            "fixups_sha256": hashlib.sha256((folder / f"{name}.fixups.tsv").read_bytes()).hexdigest(),
            "gates_sha256": hashlib.sha256((folder / f"{name}.gates.tsv").read_bytes()).hexdigest(),
        }

    def write_reports(self):
        self.manifest.write_text(json.dumps({"title_id": self.title_id, "files": self.rows}))
        self.summary = {"title_id": self.title_id,
                        "rewriter_sha256": runtime_preflight.verified_file(runtime_preflight.REWRITER),
                        "modules": self.rewrite_rows, "runtime": "not_assessed"}
        (self.rewrites / "rewrite-summary.json").write_text(json.dumps(self.summary))

    def test_three_nsos_produce_two_loadable_modules_and_relocations(self):
        report = runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)
        self.assertEqual(report["module_order"], ["main", "sdk"])
        self.assertEqual(report["excluded_modules"], ["rtld"])
        self.assertEqual(report["modules"]["main"]["relocations"], 1)
        self.assertEqual(report["modules"]["main"]["relocation_kinds"], {"1026": 1})
        self.assertEqual(report["modules"]["main"]["encoded_relocation_bytes"], 24)
        self.assertEqual(report["modules"]["main"]["flat_c_table_estimate_bytes"], 24)
        self.assertEqual(report["modules"]["main"]["gates"], 1)
        self.assertEqual(report["runtime"], "not_assessed")
        data = json.loads((self.output / "runtime-modules.json").read_text())
        self.assertEqual(data["modules"]["main"]["relocations"][0],
                         {"where": 0x3400, "kind": 1026, "symbol": 1, "addend": 0})
        self.assertEqual(data["modules"]["main"]["symbols"][1]["name"], "foo")

    def test_optional_subsdk_is_ordered_between_main_and_sdk(self):
        self.add_module("subsdk2")
        self.write_reports()
        report = runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)
        self.assertEqual(report["module_order"], ["main", "subsdk2", "sdk"])

    def test_rewrite_hash_mismatch_discards_stage(self):
        patched = self.rewrites / "main/main.patched.bin"
        with patched.open("ab") as stream:
            stream.write(b"x")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)
        self.assertFalse(self.output.exists())

    def test_excluded_rtld_rewrite_hash_is_still_verified(self):
        patched = self.rewrites / "rtld/rtld.patched.bin"
        with patched.open("ab") as stream:
            stream.write(b"x")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_rewrite_digest_is_rejected(self):
        del self.rewrite_rows["rtld"]["patched_sha256"]
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "Invalid rewrite digest"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

    def test_changed_fixups_are_rejected_even_when_patched_image_matches(self):
        with (self.rewrites / "main/main.fixups.tsv").open("a") as stream:
            stream.write("# KEY_FAKE_IDX\t1\n")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

    def test_dt_rel_is_rejected_instead_of_silently_omitted(self):
        image_path = self.rewrites / "main/main.patched.bin"
        image = bytearray(image_path.read_bytes())
        struct.pack_into("<qQ", image, 0x3100 + 11 * 16, 17, 0x3500)
        struct.pack_into("<qQ", image, 0x3100 + 12 * 16, 0, 0)
        image_path.write_bytes(image)
        self.rewrite_rows["main"]["patched_sha256"] = hashlib.sha256(image).hexdigest()
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "Unsupported relocation table"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

    def test_relr_table_cannot_point_into_generated_patch(self):
        image_path = self.rewrites / "main/main.patched.bin"
        image = bytearray(image_path.read_bytes())
        for index, pair in enumerate(((35, 8), (36, 0x8000), (37, 8), (0, 0)), 11):
            struct.pack_into("<qQ", image, 0x3100 + index * 16, *pair)
        struct.pack_into("<Q", image, 0x8000, 0x3408)
        image_path.write_bytes(image)
        self.rewrite_rows["main"]["patched_sha256"] = hashlib.sha256(image).hexdigest()
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "RELR table outside original image"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

    def test_nonempty_plt_relocations_require_declared_format(self):
        image_path = self.rewrites / "main/main.patched.bin"
        image = bytearray(image_path.read_bytes())
        struct.pack_into("<qQ", image, 0x3100 + 8 * 16, 12, 0x100)
        struct.pack_into("<qQ", image, 0x3100 + 10 * 16, 2, 24)
        struct.pack_into("<QQq", image, 0x3300, 0x3410, (1 << 32) | 1026, 0)
        image_path.write_bytes(image)
        self.rewrite_rows["main"]["patched_sha256"] = hashlib.sha256(image).hexdigest()
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "Unsupported RELA entry or PLT format"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

    def test_gate_return_must_be_unique_and_in_patch_area(self):
        gates = self.rewrites / "main/main.gates.tsv"
        gates.write_text("0x8100\tsvc\t1\t0x100\n0x8100\tsvc\t2\t0x104\n")
        self.rewrite_rows["main"]["gates"] = 2
        self.rewrite_rows["main"]["gates_sha256"] = hashlib.sha256(gates.read_bytes()).hexdigest()
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "Duplicate gate return"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

        gates.write_text("0x100\tsvc\t1\t0x100\n")
        self.rewrite_rows["main"]["gates"] = 1
        self.rewrite_rows["main"]["gates_sha256"] = hashlib.sha256(gates.read_bytes()).hexdigest()
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "Gate outside patch area"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

    def test_gate_arguments_match_instruction_widths(self):
        for kind, argument in (("svc", 65536), ("cntpct", 32), ("cntvct", -1)):
            with self.subTest(kind=kind):
                gates = self.rewrites / "main/main.gates.tsv"
                gates.write_text(f"0x8100\t{kind}\t{argument}\t0x100\n")
                self.rewrite_rows["main"]["gates_sha256"] = hashlib.sha256(gates.read_bytes()).hexdigest()
                self.write_reports()
                with self.assertRaisesRegex(ValueError, "Invalid gate argument"):
                    runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites,
                                              self.work / f"preflight-{kind}")

    def test_sysv_symbol_count_must_match_nso_extent(self):
        source = self.exefs / "main"
        raw = bytearray(source.read_bytes())
        struct.pack_into("<I", raw, 0x9c, 72)
        source.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        next(row for row in self.rows if row["name"] == "main")["sha256"] = digest
        self.rewrite_rows["main"]["nso_sha256"] = digest
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "Symbol count differs from NSO extent"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)

    def test_unsupported_relocation_does_not_publish(self):
        image_path = self.rewrites / "main/main.patched.bin"
        image = bytearray(image_path.read_bytes())
        struct.pack_into("<QQq", image, 0x3200, 0x3400, (1 << 32) | 9999, 0)
        image_path.write_bytes(image)
        self.rewrite_rows["main"]["patched_sha256"] = hashlib.sha256(image).hexdigest()
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "Unsupported relocation kind"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites, self.output)
        self.assertFalse(self.output.exists())

    def test_project_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the source project"):
            runtime_preflight.prepare(self.exefs, self.manifest, self.rewrites,
                                      ROOT / "runtime-preflight-test-output")


if __name__ == "__main__":
    unittest.main()
