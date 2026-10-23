#!/usr/bin/env python3
"""Verify macOS mapped, linked and sealed images against independent Python writes."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_tools.emit_runtime_descriptor import emit
from game_tools.verify_guest_link import expected_link
from packaging_common import outside_repository, sha256_file, verified_file


def verify(exefs: Path, runtime: Path, rewrites: Path, output: Path) -> dict:
    if sys.platform != "darwin":
        raise ValueError("Native module mapping proof requires macOS")
    exefs = outside_repository(Path(exefs), ROOT)
    runtime = outside_repository(Path(runtime), ROOT)
    rewrites = outside_repository(Path(rewrites), ROOT)
    output = outside_repository(Path(output), ROOT)
    if output.exists() or output.is_symlink():
        raise ValueError("Proof output already exists")
    compiler = shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise ValueError("C compiler not found")
    source = runtime / "runtime-modules.json"
    verified_file(source)
    data = json.loads(source.read_text())
    names = data["summary"]["module_order"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mng-native-map-", dir=output.parent) as temporary:
        stage = Path(temporary)
        header = stage / "module-table.h"
        emitted = emit(exefs, runtime, rewrites, header)
        if emitted["module_order"] != names:
            raise ValueError("Descriptor module order differs from preflight")
        first_definitions = {}
        for name in names:
            table = data["modules"][name]
            image = rewrites / name / f"{name}.patched.bin"
            verified_file(image, table["patched_sha256"])
            table["image_path"] = str(image)
            definitions = {}
            for index, symbol in enumerate(table["symbols"]):
                if index and symbol["defined"]:
                    definitions.setdefault(symbol["name"], symbol["value"])
            first_definitions[name] = definitions
        binary = stage / "native-map-probe"
        result = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime_common"), "-I", str(stage),
             *[str(ROOT / f"runtime_common/{name}.c") for name in
               ("symbol_view", "reloc_stream", "reloc_apply", "guest_link",
                "module_descriptor", "module_link", "module_image")],
             str(ROOT / "tests/native_module_map_probe.c"), "-o", str(binary)],
            capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"Native map probe compilation failed: {result.stderr[-1000:]}")
        result = subprocess.run([str(binary), str(rewrites), str(stage)],
                                capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"Native map probe failed: {result.stderr[-1000:]}")
        actual = json.loads(result.stdout)
        if set(actual.get("modules", {})) != set(names):
            raise ValueError("Native map probe module set mismatch")
        page = os.sysconf("SC_PAGESIZE")
        if actual.get("page_size") != page:
            raise ValueError("Native map probe host page size mismatch")
        bases = {name: actual["modules"][name]["base"] for name in names}
        proof = {"sample_title_id": data["summary"]["title_id"],
                 "scope": "offline macOS map/link/seal equivalence; no guest execution or frame result",
                 "module_order": names, "header_bytes": emitted["header_bytes"],
                 "map_ns": actual["map_ns"], "prepare_ns": actual["prepare_ns"],
                 "link_ns": actual["link_ns"], "seal_ns": actual["seal_ns"],
                 "permission_check_ns": actual["permission_check_ns"],
                 "page_size": page,
                 "modules": {}}
        for name in names:
            expected_hash, expected_stats = expected_link(data, name, bases,
                                                          first_definitions)
            actual_hash = sha256_file(stage / f"{name}.linked.bin")
            stats = actual["modules"][name]
            layout = data["modules"][name]["layout"]
            image_size = data["modules"][name]["file_size"]
            rx_end = (layout["TEXT_END"] + page - 1) // page * page
            ro_end = layout["DATA_OFF"] // page * page
            counts = Counter()
            for offset in range(0, (image_size + page - 1) // page * page, page):
                if offset < rx_end or offset >= layout["PATCH_OFF"]:
                    counts["rx_pages"] += 1
                elif offset < ro_end or offset >= layout["KEY_PAGE_OFF"]:
                    counts["ro_pages"] += 1
                else:
                    counts["rw_pages"] += 1
            if actual_hash != expected_hash or any(stats.get(key) != value
                                                   for key, value in expected_stats.items()) or \
                    any(stats.get(key) != counts[key] for key in
                        ("rx_pages", "ro_pages", "rw_pages")):
                raise ValueError(f"Mapped linked image differs from Python: {name}")
            proof["modules"][name] = {"base": bases[name], "linked_sha256": actual_hash,
                                      "patched_sha256": emitted["modules"][name]["patched_sha256"],
                                      **{key: stats[key] for key in expected_stats},
                                      **{key: stats[key] for key in
                                         ("rx_pages", "ro_pages", "rw_pages")}}
        staged = stage / "proof.json"
        staged.write_text(json.dumps(proof, indent=2) + "\n")
        if output.exists() or output.is_symlink():
            raise ValueError("Proof output appeared during verification")
        staged.rename(output)
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("exefs", "runtime", "rewrites", "output"):
        parser.add_argument(f"--{flag}", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        proof = verify(args.exefs, args.runtime, args.rewrites, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Native module map proof failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(proof, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
