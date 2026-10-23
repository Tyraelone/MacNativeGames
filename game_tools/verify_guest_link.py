#!/usr/bin/env python3
"""Apply verified guest relocations in C and independently compare whole images."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packaging_common import outside_repository, sha256_file, verified_file


def expected_link(data: dict, module: str, bases: dict[str, int],
                  first_definitions: dict) -> tuple[str, dict]:
    table = data["modules"][module]
    image = bytearray(Path(table["image_path"]).read_bytes())
    layout = table["layout"]
    statistics = {"relocations": 0, "local": 0, "global": 0,
                  "weak_zero": 0, "host": 0}
    for row in table["relocations"]:
        statistics["relocations"] += 1
        if row["kind"] == 1027:
            value = bases[module] + row["addend"]
        else:
            symbol = table["symbols"][row["symbol"]]
            if symbol["defined"] and symbol["binding"] != 2:
                if symbol["value"] >= layout["KEY_PAGE_OFF"]:
                    raise ValueError(f"Invalid local definition: {module}: {symbol['name']}")
                address = bases[module] + symbol["value"]
                statistics["local"] += 1
            else:
                address = None
                for other in data["summary"]["module_order"]:
                    definition = first_definitions[other].get(symbol["name"])
                    if definition is not None and definition < \
                            data["modules"][other]["layout"]["KEY_PAGE_OFF"]:
                        address = bases[other] + definition
                        statistics["global"] += 1
                        break
                if address is None:
                    if symbol["binding"] != 2:
                        raise ValueError(f"Unresolved strong symbol: {module}: {symbol['name']}")
                    address = 0
                    statistics["weak_zero"] += 1
            value = address if row["kind"] == 1026 else address + row["addend"]
        struct.pack_into("<Q", image, row["where"], value & ((1 << 64) - 1))
    return hashlib.sha256(image).hexdigest(), statistics


def verify(runtime: Path, rewrites: Path, output: Path, rounds: int = 7) -> dict:
    runtime = outside_repository(runtime, ROOT)
    rewrites = outside_repository(rewrites, ROOT)
    output = outside_repository(output, ROOT)
    if output.exists() or output.is_symlink():
        raise ValueError("Proof output already exists")
    if not 2 <= rounds <= 20:
        raise ValueError("Rounds must be between 2 and 20")
    source = runtime / "runtime-modules.json"
    verified_file(source)
    data = json.loads(source.read_text())
    names = data["summary"]["module_order"]
    if not isinstance(names, list) or not 1 <= len(names) <= 16 or \
            not all(isinstance(name, str) and
                    re.fullmatch(r"(?:main|sdk|subsdk[0-9]+)", name) for name in names) or \
            len(set(names)) != len(names):
        raise ValueError("Invalid preflight module order")
    compiler = shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise ValueError("C compiler not found")
    bases = {name: (index + 1) << 32 for index, name in enumerate(names)}
    first_definitions = {}
    for name in names:
        table = data["modules"][name]
        image_path = rewrites / name / f"{name}.patched.bin"
        verified_file(image_path, table["patched_sha256"])
        table["image_path"] = str(image_path)
        if table["layout"]["KEY_PAGE_OFF"] >= 1 << 32:
            raise ValueError(f"Module exceeds test base spacing: {name}")
        definitions = {}
        for index, symbol in enumerate(table["symbols"]):
            if index and symbol["defined"]:
                definitions.setdefault(symbol["name"], symbol["value"])
        first_definitions[name] = definitions
    output.parent.mkdir(parents=True, exist_ok=True)
    proof = {"sample_title_id": data["summary"]["title_id"],
             "scope": "offline guest-only relocation equivalence; no host ABI or gameplay result",
             "test_bases": bases, "modules": {}}
    with tempfile.TemporaryDirectory(prefix="mng-guest-link-verify-", dir=output.parent) as temporary:
        stage = Path(temporary)
        probe = stage / "guest-link-probe"
        compile_result = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime_common"),
             *[str(ROOT / f"runtime_common/{name}.c") for name in
               ("symbol_view", "guest_link", "reloc_stream", "reloc_apply")],
             str(ROOT / "tests/guest_link_probe.c"), "-o", str(probe)],
            capture_output=True, text=True)
        if compile_result.returncode:
            raise ValueError(f"Guest linker probe compilation failed: {compile_result.stderr[-500:]}")
        command = [str(probe), str(rounds), str(stage), str(len(names))]
        for name in names:
            table = data["modules"][name]
            tags, layout = table["dynamic_tags"], table["layout"]
            command += [name, table["image_path"], str(bases[name]),
                        str(layout["DATA_OFF"]), str(layout["KEY_PAGE_OFF"]),
                        str(tags["5"]), str(tags["10"]), str(tags["6"]),
                        str(len(table["symbols"])),
                        str(tags.get("36", 0)), str(tags.get("35", 0)),
                        str(tags.get("7", 0)), str(tags.get("8", 0)),
                        str(tags.get("23", 0)), str(tags.get("2", 0))]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"Guest linker probe failed: {result.stderr[-500:]}")
        metrics = json.loads(result.stdout)
        if metrics["rounds"] != rounds or set(metrics["modules"]) != set(names):
            raise ValueError("Guest linker module set or rounds mismatch")
        for name in names:
            expected_hash, expected_stats = expected_link(data, name, bases, first_definitions)
            actual_hash = sha256_file(stage / f"{name}.linked.bin")
            actual_stats = metrics["modules"][name]
            if actual_hash != expected_hash or any(actual_stats[key] != expected_stats[key]
                                                   for key in expected_stats):
                raise ValueError(f"Guest relocation mismatch: {name}")
            proof["modules"][name] = {
                "nso_sha256": data["modules"][name]["nso_sha256"],
                "patched_sha256": data["modules"][name]["patched_sha256"],
                "linked_sha256": actual_hash,
                **actual_stats,
            }
        staged = stage / "proof.json"
        staged.write_text(json.dumps(proof, indent=2) + "\n")
        if output.exists() or output.is_symlink():
            raise ValueError("Proof output appeared during verification")
        staged.rename(output)
    return proof


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--rewrites", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rounds", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        proof = verify(args.runtime, args.rewrites, args.output, args.rounds)
    except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
        print(f"Guest linker verification failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps({name: {"relocations": row["relocations"],
                             "weak_zero": row["weak_zero"]}
                      for name, row in proof["modules"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
