#!/usr/bin/env python3
"""Compare descriptor-driven C relocation with an independent flat Python writer."""

import argparse
import json
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


def index_bytes(symbol_count):
    capacity = 16
    while capacity < 2 * symbol_count:
        capacity <<= 1
    return capacity * 4


def verify(exefs: Path, runtime: Path, rewrites: Path, output: Path,
           rounds: int = 7) -> dict:
    exefs = outside_repository(Path(exefs), ROOT)
    runtime = outside_repository(Path(runtime), ROOT)
    rewrites = outside_repository(Path(rewrites), ROOT)
    output = outside_repository(Path(output), ROOT)
    if output.exists() or output.is_symlink():
        raise ValueError("Proof output already exists")
    if type(rounds) is not int or not 2 <= rounds <= 20:
        raise ValueError("Rounds must be between 2 and 20")
    compiler = shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise ValueError("C compiler not found")
    source = runtime / "runtime-modules.json"
    verified_file(source)
    data = json.loads(source.read_text())
    names = data["summary"]["module_order"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mng-descriptor-link-", dir=output.parent) as temp:
        stage = Path(temp)
        header = stage / "module-table.h"
        emitted = emit(exefs, runtime, rewrites, header)
        if emitted["module_order"] != names:
            raise ValueError("Descriptor module order differs from preflight")
        bases = {name: (index + 1) << 32 for index, name in enumerate(names)}
        first_definitions = {}
        for name in names:
            table = data["modules"][name]
            if table["layout"]["KEY_PAGE_OFF"] >= 1 << 32:
                raise ValueError(f"Module exceeds test base spacing: {name}")
            image = rewrites / name / f"{name}.patched.bin"
            verified_file(image, table["patched_sha256"])
            table["image_path"] = str(image)
            definitions = {}
            for index, symbol in enumerate(table["symbols"]):
                if index and symbol["defined"]:
                    definitions.setdefault(symbol["name"], symbol["value"])
            first_definitions[name] = definitions
        binary = stage / "descriptor-link-probe"
        compile_result = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime_common"), "-I", str(stage),
             *[str(ROOT / f"runtime_common/{name}.c") for name in
               ("symbol_view", "reloc_stream", "reloc_apply", "guest_link",
                "module_descriptor", "module_link")],
             str(ROOT / "tests/descriptor_link_probe.c"), "-o", str(binary)],
            capture_output=True, text=True)
        if compile_result.returncode:
            raise ValueError(f"Descriptor link probe compilation failed: "
                             f"{compile_result.stderr[-1000:]}")
        result = subprocess.run([str(binary), str(rounds), str(rewrites), str(stage)],
                                capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"Descriptor link probe failed: {result.stderr[-1000:]}")
        actual = json.loads(result.stdout)
        if actual.get("rounds") != rounds or set(actual.get("modules", {})) != set(names):
            raise ValueError("Descriptor link probe module set or rounds mismatch")
        proof = {"sample_title_id": data["summary"]["title_id"],
                 "scope": "offline descriptor-driven guest relocation; no mapped App or frame result",
                 "module_order": names, "rounds": rounds,
                 "header_bytes": emitted["header_bytes"],
                 "index_workspace_bytes": sum(index_bytes(len(data["modules"][name]["symbols"]))
                                              for name in names),
                 "prepare_first_ns": actual["prepare_first_ns"],
                 "prepare_warm_min_ns": actual["prepare_warm_min_ns"],
                 "link_first_ns": actual["link_first_ns"],
                 "link_warm_min_ns": actual["link_warm_min_ns"],
                 "modules": {}}
        for name in names:
            expected_hash, expected_stats = expected_link(data, name, bases,
                                                          first_definitions)
            actual_hash = sha256_file(stage / f"{name}.linked.bin")
            stats = actual["modules"][name]
            if actual_hash != expected_hash or any(stats.get(key) != value
                                                   for key, value in expected_stats.items()):
                raise ValueError(f"Descriptor linked image differs from Python: {name}")
            proof["modules"][name] = {"linked_sha256": actual_hash,
                                      "patched_sha256": emitted["modules"][name]["patched_sha256"],
                                      **stats}
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
    parser.add_argument("--rounds", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        report = verify(args.exefs, args.runtime, args.rewrites, args.output,
                        args.rounds)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Descriptor link proof failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
