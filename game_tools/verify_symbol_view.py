#!/usr/bin/env python3
"""Compare the C image symbol view with verified Python runtime tables."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packaging_common import outside_repository, verified_file


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
    compiler = shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise ValueError("C compiler not found")
    output.parent.mkdir(parents=True, exist_ok=True)
    proof = {"sample_title_id": data["summary"]["title_id"],
             "scope": "offline symbol row and lookup equivalence; no runtime or frame result",
             "modules": {}}
    names = data["summary"]["module_order"]
    if not isinstance(names, list) or not names or \
            not all(isinstance(name, str) and
                    re.fullmatch(r"(?:main|sdk|subsdk[0-9]+)", name) for name in names) or \
            len(set(names)) != len(names):
        raise ValueError("Invalid preflight module order")
    with tempfile.TemporaryDirectory(prefix="mng-symbol-verify-", dir=output.parent) as temporary:
        stage = Path(temporary)
        probe = stage / "symbol-view-probe"
        compile_result = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime_common"),
             str(ROOT / "runtime_common/symbol_view.c"),
             str(ROOT / "tests/symbol_view_probe.c"), "-o", str(probe)],
            capture_output=True, text=True)
        if compile_result.returncode:
            raise ValueError(f"Symbol probe compilation failed: {compile_result.stderr[-500:]}")
        for module in names:
            table = data["modules"][module]
            tags, layout, symbols = table["dynamic_tags"], table["layout"], table["symbols"]
            image = rewrites / module / f"{module}.patched.bin"
            verified_file(image, table["patched_sha256"])
            rows, lookups = stage / f"{module}-rows.tsv", stage / f"{module}-lookups.tsv"
            command = [str(probe), str(image), str(layout["DATA_OFF"]),
                       str(layout["KEY_PAGE_OFF"]), str(tags["5"]), str(tags["10"]),
                       str(tags["6"]), str(len(symbols)), str(rounds), str(rows), str(lookups)]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode:
                raise ValueError(f"Symbol probe failed for {module}: {result.stderr[-500:]}")
            metrics = json.loads(result.stdout)
            actual_rows = rows.read_text().splitlines()
            if len(actual_rows) != len(symbols):
                raise ValueError(f"Symbol count mismatch: {module}")
            for index, (line, expected) in enumerate(zip(actual_rows, symbols)):
                fields = line.split("\t")
                actual = (int(fields[0]), bytes.fromhex(fields[1]).decode("utf-8"),
                          int(fields[2]), int(fields[3]), bool(int(fields[4])),
                          int(fields[5]), int(fields[6]))
                want = (index, expected["name"], expected["value"], expected["size"],
                        expected["defined"], expected["binding"], expected["type"])
                if actual != want:
                    raise ValueError(f"Symbol row mismatch: {module}[{index}]")
            first = {}
            for index, symbol in enumerate(symbols):
                if index and symbol["defined"]:
                    first.setdefault(symbol["name"], (index, symbol["value"]))
            actual_lookups = {}
            for line in lookups.read_text().splitlines():
                encoded, resolved = line.split("\t")
                name = bytes.fromhex(encoded).decode("utf-8")
                if name in actual_lookups:
                    raise ValueError(f"Duplicate lookup result: {module}: {name}")
                actual_lookups[name] = int(resolved)
            expected_lookups = {name: index if value < layout["KEY_PAGE_OFF"] else 0
                                for name, (index, value) in first.items()}
            if actual_lookups != expected_lookups:
                raise ValueError(f"Symbol lookup mismatch: {module}")
            if metrics["symbols"] != len(symbols) or metrics["definitions"] != len(first) or \
                    metrics["lookup_checksum"] != metrics["flat_lookup_checksum"] or \
                    metrics["flat_row_bytes"] != 40 * len(symbols):
                raise ValueError(f"Symbol probe metrics mismatch: {module}")
            before_data = (tags["5"] + tags["10"] <= layout["DATA_OFF"] and
                           tags["6"] + 24 * len(symbols) <= layout["DATA_OFF"])
            if not before_data:
                raise ValueError(f"Symbol source table overlaps writable data: {module}")
            proof["modules"][module] = {
                "nso_sha256": table["nso_sha256"],
                "patched_sha256": table["patched_sha256"],
                "symbols_compared": len(symbols),
                "distinct_definitions_compared": len(first),
                "string_table_bytes": tags["10"],
                "symbol_table_bytes": 24 * len(symbols),
                "additional_flat_row_estimate_bytes": 40 * len(symbols),
                "source_tables_before_data": before_data,
                **metrics,
            }
        staged = stage / "proof.json"
        staged.write_text(json.dumps(proof, indent=2) + "\n")
        if output.exists() or output.is_symlink():
            raise ValueError("Proof output appeared during verification")
        staged.rename(output)
    return proof


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path,
                        help="External runtime preflight directory")
    parser.add_argument("--rewrites", required=True, type=Path,
                        help="External verified rewrite directory")
    parser.add_argument("--output", required=True, type=Path,
                        help="New external JSON proof path")
    parser.add_argument("--rounds", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        proof = verify(args.runtime, args.rewrites, args.output, args.rounds)
    except (OSError, ValueError, KeyError, IndexError, UnicodeError) as error:
        print(f"Symbol view verification failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps({name: {"symbols": row["symbols_compared"],
                             "definitions": row["distinct_definitions_compared"]}
                      for name, row in proof["modules"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
