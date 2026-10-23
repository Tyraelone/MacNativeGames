#!/usr/bin/env python3
"""Emit compact C module metadata from external, verified runtime preflight tables."""

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_tools.runtime_preflight import (parse_dynamic, parse_fixups, parse_gates,
                                          parse_relocations, parse_symbols)
from packaging_common import outside_repository, verified_file

NAME = re.compile(r"(?:main|sdk|subsdk[0-9]+)\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GATE_KINDS = {"svc": "MNG_GATE_SVC", "cntpct": "MNG_GATE_CNTPCT",
              "cntvct": "MNG_GATE_CNTVCT"}
LAYOUT_KEYS = ("TEXT_END", "RO_OFF", "DATA_OFF", "KEY_PAGE_OFF", "KEY_PAGE_SIZE",
               "PATCH_OFF")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, label):
    require(type(value) is int and 0 <= value < 1 << 64, f"Invalid {label}")
    return value


def cnum(value):
    return f"UINT64_C({value})"


def module_initializer(name, table, image, folder, source):
    layout = table["layout"]
    require(isinstance(layout, dict) and all(key in layout for key in LAYOUT_KEYS),
            f"Invalid layout: {name}")
    require(all(number(layout[key], key) == layout[key] for key in LAYOUT_KEYS),
            f"Invalid layout: {name}")
    actual_layout = parse_fixups(folder / f"{name}.fixups.tsv", len(image))
    require(layout == actual_layout, f"Rewrite layout mismatch: {name}")
    tags = table["dynamic_tags"]
    require(isinstance(tags, dict), f"Invalid dynamic tags: {name}")
    actual_tags = {str(key): value for key, value in parse_dynamic(image, layout).items()}
    require(tags == actual_tags, f"Dynamic tags mismatch: {name}")
    symbols, relocations, gates = (table[key] for key in ("symbols", "relocations", "gates"))
    require(isinstance(symbols, list) and 0 < len(symbols) <= 1_000_000 and
            isinstance(relocations, list) and isinstance(gates, list),
            f"Invalid runtime rows: {name}")
    raw_nso = source.read_bytes()[:0xa0]
    require(raw_nso[0x40:0x60].hex() == table["build_id"],
            f"NSO build ID mismatch: {name}")
    numeric_tags = {int(key): value for key, value in tags.items()}
    require(parse_symbols(image, raw_nso, layout, numeric_tags) == symbols,
            f"Symbol rows mismatch: {name}")
    for address_tag, size_tag in ((36, 35), (7, 8), (23, 2)):
        address, size = tags.get(str(address_tag), 0), tags.get(str(size_tag), 0)
        require(not size or address + size <= layout["DATA_OFF"],
                f"Relocation source table overlaps writable data: {name}")
    require(parse_relocations(image, layout, numeric_tags,
                              len(symbols)) == relocations,
            f"Relocation rows mismatch: {name}")
    require(parse_gates(folder / f"{name}.gates.tsv", len(image), layout) == gates,
            f"Gate rows mismatch: {name}")
    require(table["file_size"] == len(image), f"Image size mismatch: {name}")
    for tag in (5, 6, 10):
        require(str(tag) in tags, f"Missing dynamic tag {tag}: {name}")
    for tag in (5, 6, 10, 36, 35, 7, 8, 23, 2):
        number(tags.get(str(tag), 0), f"dynamic tag {tag}: {name}")
    require(tags["5"] + tags["10"] <= layout["DATA_OFF"] and
            tags["6"] + 24 * len(symbols) <= layout["DATA_OFF"],
            f"Symbol source tables overlap writable data: {name}")
    gate_lines = []
    for gate in sorted(gates, key=lambda row: row["return"]):
        require(gate["kind"] in GATE_KINDS, f"Invalid gate kind: {name}")
        gate_lines.append("    { .ret = %s, .original = %s, .kind = %s, .arg = %u }," %
                          (cnum(gate["return"]), cnum(gate["original"]),
                           GATE_KINDS[gate["kind"]], gate["arg"]))
    symbol_layout = ("{ .data_off = %s, .key_off = %s, .str_off = %s, .str_size = %s, "
                     ".sym_off = %s, .symbol_count = %u }") % tuple(
                         [cnum(layout["DATA_OFF"]), cnum(layout["KEY_PAGE_OFF"]),
                          cnum(tags["5"]), cnum(tags["10"]), cnum(tags["6"]), len(symbols)])
    reloc_layout = ("{ .data_off = %s, .key_off = %s, .relr_off = %s, .relr_size = %s, "
                    ".rela_off = %s, .rela_size = %s, .plt_off = %s, .plt_size = %s, "
                    ".symbol_count = %u }") % tuple(
                        [cnum(layout["DATA_OFF"]), cnum(layout["KEY_PAGE_OFF"])] +
                        [cnum(tags.get(str(tag), 0)) for tag in (36, 35, 7, 8, 23, 2)] +
                        [len(symbols)])
    gate_symbol = f"mng_gates_{name}" if gates else "NULL"
    fields = [f'.name = "{name}"', f'.sha256 = "{table["patched_sha256"]}"',
              f'.file_size = {cnum(len(image))}']
    fields += [f'.{field} = {cnum(layout[key])}' for field, key in
               (("text_end", "TEXT_END"), ("ro_off", "RO_OFF"),
                ("data_off", "DATA_OFF"), ("key_off", "KEY_PAGE_OFF"),
                ("key_page_size", "KEY_PAGE_SIZE"), ("patch_off", "PATCH_OFF"))]
    fields += [f".symbols = {symbol_layout}", f".relocations = {reloc_layout}",
               f".gates = {gate_symbol}", f".gate_count = {len(gates)}"]
    return gate_lines, "    { " + ", ".join(fields) + " },"


def emit(exefs: Path, runtime: Path, rewrites: Path, output: Path) -> dict:
    exefs = outside_repository(Path(exefs), ROOT)
    runtime = outside_repository(Path(runtime), ROOT)
    rewrites = outside_repository(Path(rewrites), ROOT)
    output_path = Path(output).expanduser()
    require(not output_path.is_symlink(), "Output is a symlink")
    output = outside_repository(output_path, ROOT)
    require(not output.exists(), "Output already exists")
    require(not output.is_relative_to(exefs) and not output.is_relative_to(runtime) and
            not output.is_relative_to(rewrites),
            "Output cannot be inside an input directory")
    source = runtime / "runtime-modules.json"
    verified_file(source)
    data = json.loads(source.read_text())
    summary, modules = data["summary"], data["modules"]
    names = summary["module_order"]
    require(isinstance(names, list) and 1 <= len(names) <= 16 and names[0] == "main" and
            all(isinstance(name, str) and NAME.fullmatch(name) for name in names) and
            len(names) == len(set(names)) and set(names) == set(modules),
            "Invalid preflight module order")
    gate_tables, module_rows = [], []
    report = {"module_order": names, "modules": {}, "scope": "offline descriptor metadata only"}
    for name in names:
        table = modules[name]
        digest = table["patched_sha256"]
        require(isinstance(digest, str) and SHA256.fullmatch(digest),
                f"Invalid patched SHA-256: {name}")
        source_digest = table["nso_sha256"]
        require(isinstance(source_digest, str) and SHA256.fullmatch(source_digest),
                f"Invalid NSO SHA-256: {name}")
        folder = rewrites / name
        path = folder / f"{name}.patched.bin"
        verified_file(path, digest)
        verified_file(exefs / name, source_digest)
        image = path.read_bytes()
        gates, row = module_initializer(name, table, image, folder, exefs / name)
        expected = summary["modules"][name]
        require(expected["symbols"] == len(table["symbols"]) and
                expected["relocations"] == len(table["relocations"]) and
                expected["gates"] == len(table["gates"]),
                f"Preflight summary mismatch: {name}")
        if gates:
            gate_tables += [f"static const MngGateDescriptor mng_gates_{name}[] = {{",
                            *gates, "};"]
        module_rows.append(row)
        report["modules"][name] = {"symbols": len(table["symbols"]),
                                   "relocations": len(table["relocations"]),
                                   "gates": len(table["gates"]),
                                   "patched_sha256": digest}
    lines = ["/* Generated from verified external runtime preflight data. */",
             "#pragma once", '#include "module_descriptor.h"',
             f"#define MNG_MODULE_COUNT {len(names)}", *gate_tables,
             "static const MngModuleDescriptor mng_modules[MNG_MODULE_COUNT] = {",
             *module_rows, "};", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mng-descriptor-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        staged.write_text("\n".join(lines))
        require(not output.exists() and not output.is_symlink(), "Output already exists")
        staged.rename(output)
    report["header_bytes"] = output.stat().st_size
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("exefs", "runtime", "rewrites", "output"):
        parser.add_argument(f"--{flag}", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = emit(args.exefs, args.runtime, args.rewrites, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Runtime descriptor emission failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
