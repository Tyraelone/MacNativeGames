"""Mario's embedded shaders can be found before any save is played."""

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import compression.zstd as zstd


SOURCE = Path(__file__).resolve().parents[1] / "games/mario_wonder/prepare_static_shader_seed.py"
spec = importlib.util.spec_from_file_location("mario_static_seed", SOURCE)
static_seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(static_seed)


def one_vertex_shader():
    data = bytearray(0x1400)
    data[:8] = b"BNSH\0\0\0\0"
    data[12:14] = b"\xff\xfe"
    data[96:100] = b"grsc"
    struct.pack_into("<I", data, 28, len(data))
    struct.pack_into("<IQ", data, 124, 1, 0xc0)
    struct.pack_into("<Q", data, 0xc0 + 16, 0x100)
    struct.pack_into("<Q", data, 0x100 + 8, 0x200)
    struct.pack_into("<QQII", data, 0x208, 0x300, 0xc00, 0x100, 0x880)
    struct.pack_into("<II", data, 0x300 + 0x700, 0x80, 0x100)
    struct.pack_into("<I", data, 0x300 + 0x714, 0)
    data[0xc00:0xd00] = b"\x7f" * 0x100
    return bytes(data)


class MarioStaticInventoryTests(unittest.TestCase):
    def test_embedded_shader_in_effect_is_indexed_by_runtime_hash(self):
        shader = one_vertex_shader()
        payload = b"effect header" + shader + b"effect trailer"
        packed = zstd.compress(payload)
        with tempfile.TemporaryDirectory(prefix="mario-static-inventory-") as tmp:
            romfs = Path(tmp)
            (romfs / "romfs.bin").write_bytes(packed + packed)
            (romfs / "index.json").write_text(json.dumps({
                "status": "pass", "romfs_sha256": "f" * 64,
                "files": [
                    {"path": "Effect/Scene.esetb.byml.zs", "offset": 0, "size": len(packed)},
                    {"path": "Layout/Menu.blarc.zs", "offset": len(packed), "size": len(packed)},
                ],
            }))
            identity, found = static_seed.inventory(romfs)

        expected = hashlib.sha256(shader[0x300:0xb80] + shader[0xc00:0xd00]).hexdigest()
        self.assertEqual(identity, "f" * 64)
        self.assertEqual(list(found), [expected])
        self.assertEqual(found[expected][:3], ("vs", shader[0x300:0xb80], shader[0xc00:0xd00]))

    def test_preparation_publishes_usable_seed_from_verified_romfs(self):
        shader = one_vertex_shader()
        packed = zstd.compress(b"effect" + shader)
        with tempfile.TemporaryDirectory(prefix="mario-static-prepare-") as tmp:
            root = Path(tmp)
            romfs, output = root / "romfs", root / "seed"
            romfs.mkdir()
            (romfs / "romfs.bin").write_bytes(packed)
            (romfs / "index.json").write_text(json.dumps({
                "status": "pass", "romfs_sha256": "f" * 64,
                "files": [{"path": "Effect/Scene.esetb.byml.zs", "offset": 0, "size": len(packed)}],
            }))
            translator = root / "translator"
            translator.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])
for line in sys.stdin:
    item = json.loads(line)
    (out / (item['variant'] + '_b.metal')).write_text('// translated\\n')
    (out / (item['variant'] + '_b.json')).write_text(json.dumps({
        'chain': 'totk-native-v4-unverified', 'stage': item['stage'],
        'entry': 'main', 'deps': {'attr': {'0': 'float'}}}))
    (out / (item['variant'] + '.res.json')).write_text('{}')
    (out / (item['variant'] + '.spv')).write_bytes(b'intermediate')
    print(json.dumps({'ok': True}), flush=True)
""")
            translator.chmod(0o755)
            spirv = root / "spirv-cross"
            spirv.write_text("binary")

            report = static_seed.prepare(romfs, output, translator, spirv)

            self.assertEqual(report["shaders"], 1)
            variants = list(output.glob("*.variants"))
            self.assertEqual(len(variants), 1)
            name = json.loads(variants[0].read_text())[0]["variant"]
            self.assertTrue((output / f"{name}_b.metal").exists())
            self.assertEqual((output / "pso_manifest.tsv").read_text(), f"S\t{name}_b\t0\n")
            self.assertFalse(list(output.glob("*.code")))
            self.assertFalse(list(output.glob("*.res.json")))
            self.assertFalse(list(output.glob("*.spv")))


if __name__ == "__main__":
    unittest.main()
