#!/usr/bin/env python3
"""Inspect game code identity without claiming an unverified native port."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from build_game import TARGETS

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "games/totk/scripts"))
from extract_exefs import (common_tickets, container_entries, load_keys,
                           nca_inventory, program_nca)


def select_program(source: Path, key_file: Path, title_id: str | None = None) -> dict:
    """Validate the container's selected Program and base/update identity."""
    keys = load_keys(key_file)
    with source.open("rb") as stream:
        container, entries = container_entries(stream, source.stat().st_size)
        common_tickets(stream, entries)
        records = nca_inventory(stream, entries, keys)
    programs = [(record, header) for record, header in records
                if record["content_type"] == 0]
    if title_id is None:
        if len(programs) != 1:
            raise ValueError("Expected one Program NCA; use --title-id for a combined XCI")
        title_id = programs[0][0]["title_id"]
    title_id = title_id.upper()
    selected = [(record, header) for record, header in programs
                if record["title_id"] == title_id]
    if container == "xci" and len(programs) > 1 and any(
        any(header[0x400 + i * 512 + 4] == 4 for i in range(4))
        for _, header in selected
    ):
        raise ValueError("Combined update XCI is unsupported; provide a separate update NSP")
    if len(selected) != 1:
        raise ValueError(f"Expected one Program NCA for title ID {title_id}")
    header = selected[0][1]
    update = any(header[0x400 + i * 512 + 4] == 4 for i in range(4))
    program_nca(records, update=update, title_id=title_id,
                allow_combined=container == "xci" and not update)
    metadata = sorted(record["title_id"] for record, _ in records
                      if record["content_type"] == 1)
    if update and metadata != [f"{int(title_id, 16) + 0x800:016X}"]:
        raise ValueError("Update metadata title ID does not match the base title")
    return {"container": container, "title_id": title_id,
            "package_kind": "update" if update else "base",
            "metadata_title_ids": metadata}


def registered_profiles():
    """Read pinned profiles only from registered target directories."""
    for target, details in TARGETS.items():
        title_id, _, _, directory = details
        for path in sorted(directory.glob("expected-v*.json")):
            expected = json.loads(path.read_text())
            hashes = expected.get("exefs_sha256") if isinstance(expected, dict) else None
            if (not isinstance(hashes, dict) or not hashes or
                    not isinstance(expected.get("display_version"), str) or
                    not expected["display_version"] or
                    any(not isinstance(name, str) or not name or
                        not isinstance(digest, str) or len(digest) != 64 or
                        any(char not in "0123456789abcdef" for char in digest)
                        for name, digest in hashes.items())):
                raise ValueError(f"Invalid ExeFS profile: {path}")
            if expected.get("title_id") != title_id:
                raise ValueError(f"Profile title ID mismatch: {path}")
            yield target, expected


def match_profile(title_id: str, files: dict[str, str]) -> dict | None:
    """Only complete pinned ExeFS hashes establish a known build version."""
    matches = [{"target": target, "version": expected["display_version"]}
               for target, expected in registered_profiles()
               if expected["title_id"] == title_id and expected["exefs_sha256"] == files]
    if len(matches) > 1:
        raise ValueError("Ambiguous exact ExeFS profile")
    return matches[0] if matches else None


def match_code_profile(title_id: str, files: dict[str, str]) -> dict | None:
    """Show a uniquely matching code set while keeping metadata mismatches visible."""
    candidates = []
    for target, expected in registered_profiles():
        want = expected["exefs_sha256"]
        if expected["title_id"] != title_id or set(files) != set(want) or files == want:
            continue
        code = [name for name in want if not name.endswith(".npdm")]
        if all(files[name] == want[name] for name in code):
            candidates.append({"target": target, "version": expected["display_version"],
                               "mismatched_files": sorted(name for name in want
                                                          if files[name] != want[name])})
    return candidates[0] if len(candidates) == 1 else None


def report_from_artifacts(identity: dict, manifest: dict, modules: list,
                          dependencies: dict) -> dict:
    """Summarize verified code separately from untested runtime capabilities."""
    rows = manifest["files"]
    files = {row["name"]: row["sha256"] for row in rows}
    if len(files) != len(rows) or not modules:
        raise ValueError("Incomplete ExeFS or NSO inventory")
    if "main" not in dependencies["modules"]:
        raise ValueError("Dependency map has no main module")
    profile = match_profile(identity["title_id"], files)
    known_titles = {details[0] for details in TARGETS.values()}
    status = ("verified_exefs_profile" if profile else
              "known_title_unknown_version" if identity["title_id"] in known_titles
              else "unported_title")
    verified_hashes = sum(bool(module["segment_hashes_verified"]) for module in modules)
    nso_hash_status = ("pass" if verified_hashes == len(modules) else
                       "partial" if verified_hashes else "not_present")
    checks = {"container_header": "pass", "exefs_hash_chain": "pass",
              "nca_rsa_signatures": "not_checked",
              "nso_segment_hashes": nso_hash_status}
    checks.update({name: "not_assessed" for name in (
        "romfs", "host_services", "nvn", "media", "rewrites", "gameplay_performance")})
    return {"format": 1, **identity, "status": status, "profile": profile,
            "code_match": None if profile else match_code_profile(identity["title_id"], files),
            "exefs_sha256": files,
            "modules": [{"name": module["module"], "build_id": module["build_id"],
                         "segment_hashes_verified": module["segment_hashes_verified"]}
                        for module in modules],
            "main_import_groups": dependencies["modules"]["main"]["group_counts"],
            "checks": checks,
            "scope": "Code identity and static imports only; no RomFS or native runtime verification"}


def _run_tool(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip().splitlines()
        raise ValueError(f"{Path(command[1]).name} failed: {detail[-1] if detail else error.returncode}") from None


def inspect(source: Path, key_file: Path, title_id: str | None = None,
            *, temp_root: Path | None = None) -> dict:
    """Run existing validators in an external disposable workspace."""
    source = Path(source)
    key_file = Path(key_file)
    before = source.stat()
    identity = select_program(source, key_file, title_id)
    parent = Path(temp_root or tempfile.gettempdir()).resolve()
    if parent.is_relative_to(ROOT):
        raise ValueError("Inspection temporary data must stay outside the source checkout")
    with tempfile.TemporaryDirectory(prefix="mng-inspect-", dir=parent) as workspace:
        work = Path(workspace)
        exefs = work / "exefs"
        command = [sys.executable, str(ROOT / "games/totk/scripts/extract_exefs.py"),
                   str(source), "--keys", str(key_file), "--title-id", identity["title_id"],
                   "--output", str(exefs)]
        if identity["package_kind"] == "update":
            command.append("--update")
        _run_tool(command)
        inventory = work / "elf"
        _run_tool([sys.executable, str(ROOT / "games/totk/scripts/prepare_modules.py"),
                   str(exefs), "--output", str(inventory)])
        dependency_file = work / "dependency-map.json"
        _run_tool([sys.executable, str(ROOT / "games/totk/scripts/map_dependencies.py"),
                   str(inventory), "--output", str(dependency_file)])
        manifest = json.loads((work / "extraction-manifest.json").read_text())
        modules = json.loads((inventory / "modules.json").read_text())
        dependencies = json.loads(dependency_file.read_text())
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Game file changed during inspection")
        return report_from_artifacts(identity, manifest, modules, dependencies)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="one base or update XCI/NSP")
    parser.add_argument("--keys", required=True, type=Path, help="local prod.keys path")
    parser.add_argument("--title-id", help="select a base title from a combined XCI")
    args = parser.parse_args(argv)
    try:
        report = inspect(args.game, args.keys, args.title_id)
    except (ValueError, OSError) as error:
        print(f"Inspect failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
