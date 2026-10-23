#!/usr/bin/env python3
"""Find Mario's embedded NVN programs in the verified, external RomFS.

The packages contain game assets. Keep all extracted data and generated
shaders in the external build directory, never in the source checkout.
"""

import argparse
import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import compression.zstd as zstd


_HELPER = Path(__file__).resolve().parents[1] / "totk/scripts/prepare_shader_seed.py"
_SPEC = importlib.util.spec_from_file_location("totk_prepare_shader_seed", _HELPER)
_SEED = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SEED)
CHAIN = "totk-native-v4-unverified"
ANSWERS = {"tex": {}, "img": {}, "attr": {}, "fout": {}}
SUFFIX = hashlib.sha256(json.dumps(ANSWERS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def inventory(romfs: Path):
    """Return verified RomFS identity and unique embedded programs by runtime hash."""
    index = json.loads((romfs / "index.json").read_text())
    if index.get("status") != "pass" or not index.get("romfs_sha256"):
        raise ValueError("RomFS has not passed integrity verification")
    shaders = {}
    with (romfs / "romfs.bin").open("rb") as stream:
        for entry in index["files"]:
            if not entry["path"].endswith(".zs"):
                continue
            stream.seek(entry["offset"])
            raw = stream.read(entry["size"])
            if len(raw) != entry["size"]:
                raise ValueError("short RomFS asset read")
            frame = zstd.get_frame_info(raw)
            if frame.decompressed_size is None or frame.decompressed_size > 512 << 20:
                raise ValueError("unbounded RomFS asset")
            data = zstd.decompress(raw)
            pos = 0
            while True:
                pos = data.find(b"BNSH\0\0\0\0", pos)
                if pos < 0:
                    break
                size = struct.unpack_from("<I", _SEED.checked(data, pos + 28, 4))[0]
                for key, stage, control, code in _SEED.bnsh_shaders(_SEED.checked(data, pos, size)):
                    shaders.setdefault(key, (stage, control, code, entry["path"]))
                pos += size
    if not shaders:
        raise ValueError("no embedded NVN shaders found")
    return index["romfs_sha256"], shaders


def prepare(romfs: Path, output: Path, translator: Path, spirv_cross: Path):
    """Translate the finite static set offline; publish only complete variants."""
    if output.exists():
        raise FileExistsError(output)
    romfs_hash, shaders = inventory(romfs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mario-static-seed-", dir=output.parent) as tmp:
        staging = Path(tmp)
        process = subprocess.Popen(
            [str(translator), "--service", "--spirv-cross", str(spirv_cross),
             "--out", str(staging), "--chain", CHAIN],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        rows, failed, completed = [], [], []
        try:
            for number, (key, (stage, control, code, source)) in enumerate(sorted(shaders.items()), 1):
                variant = key + "-" + SUFFIX
                c1, length = struct.unpack_from("<II", control, 0x700)
                code_path = staging / (variant + ".code")
                code_path.write_bytes(code[0 if stage == "cs" else 0x30:length])
                request = dict(variant=variant, stage=stage, code=str(code_path),
                               c1=code[c1:length].hex(), depth_minus_w=True, **ANSWERS)
                if stage == "cs":
                    request["local"] = list(struct.unpack_from("<III", control, 0x748))
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                response = process.stdout.readline()
                code_path.unlink()
                if not response:
                    raise ValueError("shader translation service exited unexpectedly")
                reply = json.loads(response)
                metal, reflection = staging / (variant + "_b.metal"), staging / (variant + "_b.json")
                if not reply.get("ok"):
                    metal.unlink(missing_ok=True)
                    reflection.unlink(missing_ok=True)
                    failed.append({"key": key, "source": source, "error": reply.get("error")})
                    continue
                meta = json.loads(reflection.read_text())
                if (meta.get("chain") != CHAIN or meta.get("stage") != stage or
                        not isinstance(meta.get("deps"), dict) or not metal.is_file()):
                    raise ValueError(f"incomplete translated shader: {key}")
                (staging / (key + ".variants")).write_text(json.dumps(
                    [{"variant": variant, "deps": meta["deps"]}], separators=(",", ":")) + "\n")
                completed.append(variant)
                rows.append(f"S\t{variant}_b\t{ {'vs': 0, 'ps': 1, 'cs': 5}[stage] }")
                if stage == "cs":
                    rows.append(f"C\t{variant}_b")
                if number % 500 == 0:
                    print(f"prepared {number}/{len(shaders)} static shaders; {len(failed)} skipped", flush=True)
        finally:
            process.stdin.close()
            process.wait()
            process.stdout.close()
        if process.returncode:
            raise ValueError(f"shader translation service exited with status {process.returncode}")
        if not rows:
            raise ValueError("no static shaders translated")
        wanted = {name for variant in completed for name in (
            variant + "_b.metal", variant + "_b.json", variant.split("-")[0] + ".variants")}
        for path in staging.iterdir():
            if path.name not in wanted:
                path.unlink()
        (staging / "pso_manifest.tsv").write_text("\n".join(rows) + "\n")
        files = {p.name: _SEED.digest(p.read_bytes()) for p in sorted(staging.iterdir())}
        report = {"schema": 1, "chain": CHAIN, "source_romfs_sha256": romfs_hash,
                  "discovered": len(shaders), "shaders": len(list(staging.glob("*_b.metal"))),
                  "skipped": failed, "files": files}
        (staging / "seed-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        staging.rename(output)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("romfs", "output", "translator", "spirv-cross"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    repo = Path(__file__).resolve().parents[2]
    if output == repo or repo in output.parents:
        parser.error("generated shader seed must be outside the source tree")
    report = prepare(args.romfs.expanduser().resolve(), output,
                     args.translator.expanduser().resolve(), args.spirv_cross.expanduser().resolve())
    print(f"static shader seed ready: {report['shaders']} of {report['discovered']} programs", flush=True)


if __name__ == "__main__":
    main()
