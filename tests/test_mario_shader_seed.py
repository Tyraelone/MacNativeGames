"""A recorded Mario graphics cache can be packaged without personal saves."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "games/mario_wonder/build_app.py"
spec = importlib.util.spec_from_file_location("mario_build_app", SOURCE)
build_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_app)


class MarioShaderSeedTests(unittest.TestCase):
    def test_static_and_recorded_variants_share_an_index_in_final_seed(self):
        with tempfile.TemporaryDirectory(prefix="mario-merge-seed-") as temp:
            root = Path(temp)
            key = "a" * 64
            variants = [key + "-" + char * 12 for char in "bc"]
            seeds = []
            for label, variant in zip(("recorded", "static"), variants):
                cache, output = root / f"{label}-cache", root / f"{label}-seed"
                cache.mkdir()
                deps = {"attr": {"6": "uint"}} if label == "recorded" else {"attr": {"6": "float"}}
                (cache / f"{variant}_b.metal").write_text(f"// {label}\n")
                (cache / f"{variant}_b.json").write_text(json.dumps({
                    "chain": build_app.SHADER_CHAIN, "stage": "vs", "entry": "main", "deps": deps,
                }))
                (cache / f"{key}.variants").write_text(json.dumps([{"variant": variant, "deps": deps}]))
                (cache / "pso_collected.tsv").write_text(f"S\t{variant}_b\t0\n")
                build_app.prepare_recorded_seed(cache, output)
                seeds.append(output)

            combined = root / "combined"
            report = build_app.merge_shader_seeds(seeds, combined)

            self.assertEqual(report["shaders"], 2)
            rows = json.loads((combined / f"{key}.variants").read_text())
            self.assertEqual([row["variant"] for row in rows], variants)
            self.assertEqual((combined / "pso_manifest.tsv").read_text().splitlines(),
                             [f"S\t{variant}_b\t0" for variant in variants])
            build_app.verify_recorded_seed(combined)

    def test_seed_identity_changes_when_shader_changes_without_new_pso_row(self):
        with tempfile.TemporaryDirectory(prefix="mario-seed-id-") as temp:
            cache = Path(temp)
            (cache / "pso_collected.tsv").write_text("R\t1234\n")
            index = cache / ("a" * 64 + ".variants")
            index.write_text("[]\n")
            before = build_app.recorded_cache_identity(cache)
            index.write_text('[{"variant":"new"}]\n')
            self.assertNotEqual(build_app.recorded_cache_identity(cache), before)

    def test_recorded_variant_becomes_verified_seed_without_profile_files(self):
        with tempfile.TemporaryDirectory(prefix="mario-seed-") as temp:
            root = Path(temp)
            cache, output = root / "cache", root / "seed"
            cache.mkdir()
            key = "a" * 64
            variant = key + "-" + "b" * 12
            (cache / f"{variant}_b.metal").write_text("vertex float4 main() { return 0; }\n")
            (cache / f"{variant}_b.json").write_text(json.dumps({
                "chain": "totk-native-v4-unverified", "stage": "vs", "entry": "main", "deps": {}
            }))
            (cache / f"{key}.variants").write_text(json.dumps([{"variant": variant, "deps": {}}]))
            (cache / "pso_collected.tsv").write_text(f"S\t{variant}_b\t0\n")
            (cache / "account.uid").write_bytes(b"personal")

            report = build_app.prepare_recorded_seed(cache, output)

            self.assertEqual(report["shaders"], 1)
            self.assertEqual(set(report["files"]), {
                f"{variant}_b.metal", f"{variant}_b.json", f"{key}.variants", "pso_manifest.tsv"
            })
            self.assertEqual((output / "pso_manifest.tsv").read_text(), f"S\t{variant}_b\t0\n")
            self.assertFalse((output / "account.uid").exists())
            for name, expected in report["files"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            build_app.verify_recorded_seed(output)
            (output / "account.uid").write_bytes(b"personal")
            with self.assertRaisesRegex(ValueError, "unlisted"):
                build_app.verify_recorded_seed(output)
            (output / "account.uid").unlink()
            (output / f"{variant}_b.metal").write_text("tampered")
            with self.assertRaises(ValueError):
                build_app.verify_recorded_seed(output)

    def test_wrong_translation_chain_is_not_published(self):
        with tempfile.TemporaryDirectory(prefix="mario-seed-") as temp:
            root = Path(temp)
            cache, output = root / "cache", root / "seed"
            cache.mkdir()
            key = "a" * 64
            variant = key + "-" + "b" * 12
            (cache / f"{variant}_b.metal").write_text("vertex float4 main() { return 0; }\n")
            (cache / f"{variant}_b.json").write_text(json.dumps({
                "chain": "old-chain", "stage": "vs", "entry": "main", "deps": {}
            }))
            (cache / f"{key}.variants").write_text(json.dumps([{"variant": variant, "deps": {}}]))
            (cache / "pso_collected.tsv").write_text(f"S\t{variant}_b\t0\n")

            with self.assertRaises(ValueError):
                build_app.prepare_recorded_seed(cache, output)
            self.assertFalse(output.exists())

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "needs Metal compiler")
    def test_precompiled_library_is_named_by_exact_source_hash(self):
        with tempfile.TemporaryDirectory(prefix="mario-metal-") as temp:
            root = Path(temp)
            seed, libs = root / "seed", root / "libs"
            seed.mkdir()
            source = b"#include <metal_stdlib>\nusing namespace metal;\nvertex float4 main0(uint id [[vertex_id]]) { return float4(float(id), 0, 0, 1); }\n"
            (seed / ("a" * 64 + "-" + "b" * 12 + "_b.metal")).write_bytes(source)

            built, failed = build_app.compile_recorded_libraries(seed, libs, jobs=1)

            self.assertEqual((built, failed), (1, 0))
            self.assertTrue((libs / (hashlib.sha256(source).hexdigest() + ".metallib")).read_bytes().startswith(b"MTLB"))


if __name__ == "__main__":
    unittest.main()
