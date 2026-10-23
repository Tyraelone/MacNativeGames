#!/usr/bin/env python3
"""Summarize NVN BindProgram diagnostics without copying game logs into the repo."""

import argparse
import json
import re
from pathlib import Path


MARKER = re.compile(r"\[bindprog\]")
HEADER = re.compile(
    r"\[bindprog\]\s+frame=(\d+)\s+mask=(0x[0-9a-fA-F]+)"
    r"\s+prog=(\S+)\s+serial=(\d+)\s+nstage=(\d+)"
)
NULL_PROGRAMS = {"0", "0x0", "(nil)", "nil", "NULL"}
KNOWN_STAGE_BITS = 0x3F
LOGGER_LIMIT = 20000


def graphics_mode(sources, unknown):
    vertex, fragment = sources[:2]
    if vertex is unknown or fragment is unknown:
        return "unknown"
    if vertex is not None and fragment is not None and vertex != fragment:
        return "divergent"
    if (vertex is None) != (fragment is None):
        return "incomplete"
    return "same_or_empty"


def analyze_lines(lines):
    report = {
        "records": 0,
        "malformed_records": 0,
        "frames": {"first": None, "last": None},
        "masks": {},
        "graphics_then_non_graphics_null": 0,
        "partial_graphics_records": 0,
        "compute_program_records": 0,
        "unknown_bit_records": 0,
        "divergent_graphics_transitions": 0,
        "incomplete_graphics_transitions": 0,
        "example_lines": {
            "partial_graphics": [], "unknown_bits": [], "malformed": [],
            "divergent_graphics": [], "incomplete_graphics": [],
        },
        "logger_record_limit_reached": False,
        "coverage_note": (
            "diagnostic sample only; absence does not prove game-wide absence; "
            "stage sources follow masks and program identity, not shader contents or draw commands"
        ),
    }
    previous = None
    unknown = object()
    sources = [unknown] * 6
    for line_number, line in enumerate(lines, 1):
        markers = list(MARKER.finditer(line))
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(line)
            match = HEADER.match(line, marker.start(), end)
            if not match:
                report["malformed_records"] += 1
                if len(report["example_lines"]["malformed"]) < 5:
                    report["example_lines"]["malformed"].append(line_number)
                previous = None
                sources = [unknown] * 6
                continue
            frame, mask_text, program_text, serial_text, _ = match.groups()
            frame = int(frame)
            mask = int(mask_text, 16)
            has_program = program_text not in NULL_PROGRAMS
            report["records"] += 1
            frames = report["frames"]
            frames["first"] = frame if frames["first"] is None else min(frames["first"], frame)
            frames["last"] = frame if frames["last"] is None else max(frames["last"], frame)
            key = hex(mask)
            counts = report["masks"].setdefault(key, {"program": 0, "null": 0})
            counts["program" if has_program else "null"] += 1
            if (mask & 0x3) in (0x1, 0x2):
                report["partial_graphics_records"] += 1
                if len(report["example_lines"]["partial_graphics"]) < 5:
                    report["example_lines"]["partial_graphics"].append(line_number)
            if mask & 0x20 and has_program:
                report["compute_program_records"] += 1
            if mask & ~KNOWN_STAGE_BITS:
                report["unknown_bit_records"] += 1
                if len(report["example_lines"]["unknown_bits"]) < 5:
                    report["example_lines"]["unknown_bits"].append(line_number)
            before = graphics_mode(sources, unknown)
            for stage in range(6):
                if mask & (1 << stage):
                    sources[stage] = (program_text, serial_text) if has_program else None
            after = graphics_mode(sources, unknown)
            if after != before and after in ("divergent", "incomplete"):
                report[f"{after}_graphics_transitions"] += 1
                example = report["example_lines"][f"{after}_graphics"]
                if len(example) < 5:
                    example.append(line_number)
            if (
                previous is not None
                and previous[0] == frame
                and (previous[1] & 0x3) == 0x3
                and previous[2]
                and not has_program
                and (mask & 0x3) == 0
            ):
                report["graphics_then_non_graphics_null"] += 1
            previous = (frame, mask, has_program)
    report["logger_record_limit_reached"] = (
        report["records"] + report["malformed_records"] >= LOGGER_LIMIT
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="external NVN diagnostic log")
    args = parser.parse_args()
    with args.log.open(encoding="utf-8", errors="replace") as source:
        report = analyze_lines(source)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
