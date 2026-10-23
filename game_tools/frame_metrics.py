#!/usr/bin/env python3
"""Summarize an external NVN TSV frame window without launching a game."""

import argparse
import json
import math
from pathlib import Path


METRICS = {"@frame_ms", "@gpu_ms", "@pso_new"}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def summarize_tsv(path: Path, first: int, last: int,
                  budget_ms: float = 1000 / 60) -> dict:
    if first < 0 or last < first:
        raise ValueError("Expected a nonnegative, ordered frame range")
    if not math.isfinite(budget_ms) or budget_ms <= 0:
        raise ValueError("Frame budget must be positive and finite")

    frames: dict[int, float] = {}
    gpu: dict[int, float] = {}
    pso: dict[int, float] = {}
    seen: set[tuple[int, str]] = set()
    invalid_rows = invalid_frame_rows = 0
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 2 or parts[1] not in METRICS:
                continue
            try:
                frame = int(parts[0])
            except ValueError:
                continue
            if not first <= frame <= last:
                continue
            metric = parts[1]
            key = (frame, metric)
            if key in seen:
                raise ValueError(f"duplicate {metric} at frame {frame}")
            seen.add(key)
            if len(parts) == 3:
                try:
                    value = float(parts[2])
                except ValueError:
                    value = math.nan
            else:
                value = math.nan
            if not math.isfinite(value) or value < 0 or (metric == "@frame_ms" and value == 0):
                invalid_rows += 1
                invalid_frame_rows += metric == "@frame_ms"
                continue
            {"@frame_ms": frames, "@gpu_ms": gpu, "@pso_new": pso}[metric][frame] = value

    expected = last - first + 1
    elapsed = list(frames.values())
    gpu_values = list(gpu.values())
    over = sum(value > budget_ms for value in elapsed)
    return {
        "first_frame": first, "last_frame": last,
        "expected_frames": expected, "measured_frames": len(elapsed),
        "missing_frame_count": expected - len(elapsed),
        "invalid_rows": invalid_rows, "invalid_frame_rows": invalid_frame_rows,
        "complete_frame_coverage": len(elapsed) == expected and not invalid_frame_rows,
        "budget_ms": budget_ms,
        "fps_mean": 1000 * len(elapsed) / sum(elapsed) if elapsed else None,
        "frame_ms_p50": percentile(elapsed, .5),
        "frame_ms_p95": percentile(elapsed, .95),
        "frame_ms_p99": percentile(elapsed, .99),
        "frame_ms_max": max(elapsed, default=None),
        "over_budget_frames": over,
        "over_budget_fraction": over / len(elapsed) if elapsed else None,
        "gpu_measured_frames": len(gpu_values),
        "gpu_missing_frames": expected - len(gpu_values),
        "gpu_ms_p50": percentile(gpu_values, .5),
        "gpu_ms_p95": percentile(gpu_values, .95),
        "gpu_ms_p99": percentile(gpu_values, .99),
        "gpu_ms_max": max(gpu_values, default=None),
        "pso_measured_frames": len(pso),
        "pso_new_total": sum(pso.values()) if pso else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tsv", type=Path, help="external DM_NVN_TSV log")
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--last", type=int, required=True)
    parser.add_argument("--budget-ms", type=float, default=1000 / 60)
    args = parser.parse_args()
    print(json.dumps(summarize_tsv(args.tsv, args.first, args.last, args.budget_ms),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
