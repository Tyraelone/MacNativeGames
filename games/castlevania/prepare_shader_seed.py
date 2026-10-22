#!/usr/bin/env python3
"""Snapshot verified Castlevania runtime shaders into an external App seed.

The input is a cache collected by playing the verified main game. Both the
cache and output stay outside the source project.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from build_app import REPO, ROMFS_SHA256

CHAIN = "totk-native-v4-unverified"
SHADER = re.compile(r"[0-9a-f]{64}-[0-9a-f]{12}_b")
INDEX = re.compile(r"[0-9a-f]{64}\.variants")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cache, out = args.cache.expanduser().resolve(), args.out.expanduser().absolute()
    if cache.is_relative_to(REPO) or out.is_relative_to(REPO) or out.exists():
        raise SystemExit("Cache and new seed output must be outside the source project")
    if not cache.is_dir() or cache.is_symlink():
        raise SystemExit(f"Missing regular shader cache directory: {cache}")
    stems = sorted(p.name[:-6] for p in cache.glob("*_b.metal") if SHADER.fullmatch(p.stem))
    if not stems:
        raise SystemExit("No translated game shaders in cache")
    for stem in stems:
        reflection = cache / (stem + ".json")
        if not reflection.is_file() or reflection.is_symlink():
            raise SystemExit(f"Missing shader reflection: {reflection}")
        data = json.loads(reflection.read_text())
        if data.get("key") != stem or data.get("chain") != CHAIN or data.get("stage") not in ("vs", "ps", "cs"):
            raise SystemExit(f"Incompatible shader reflection: {reflection}")
    manifest_rows = []
    collected = cache / "pso_collected.tsv"
    if collected.is_file():
        manifest_rows = sorted({line for line in collected.read_text().splitlines()
                                if line.startswith(("S\t", "R\t", "C\t"))})
    staging = out.with_name(out.name + ".partial")
    if staging.exists():
        raise SystemExit(f"Staging path already exists: {staging}")
    staging.mkdir(parents=True)
    files = {}
    for stem in stems:
        for suffix in (".metal", ".json"):
            name = stem + suffix
            source = cache / name
            if source.is_symlink() or not source.is_file():
                raise SystemExit(f"Invalid shader source: {source}")
            shutil.copy2(source, staging / name)
            files[name] = digest(staging / name)
    for source in sorted(cache.glob("*.variants")):
        if not INDEX.fullmatch(source.name) or source.is_symlink():
            raise SystemExit(f"Invalid shader index: {source}")
        rows = json.loads(source.read_text())
        if not isinstance(rows, list):
            raise SystemExit(f"Invalid shader index: {source}")
        rows = [row for row in rows if isinstance(row, dict) and
                row.get("variant", "") + "_b" in stems and isinstance(row.get("deps"), dict)]
        if not rows:
            continue
        target = staging / source.name
        target.write_text(json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n")
        files[source.name] = digest(target)
    pso = staging / "pso_manifest.tsv"
    pso.write_text("# Castlevania 1.1.0 gameplay pipelines; " + CHAIN + "\n" + "\n".join(manifest_rows) + "\n")
    files[pso.name] = digest(pso)
    manifest = {"schema": 1, "chain": CHAIN, "shaders": len(stems),
                "source_romfs_sha256": ROMFS_SHA256, "files": files}
    (staging / "seed-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    staging.rename(out)
    print(f"{out}: {len(stems)} shaders, {len(manifest_rows)} pipeline rows")


if __name__ == "__main__":
    main()
