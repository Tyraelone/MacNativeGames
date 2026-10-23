# Direct Relocation Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate reading relocation records directly from a verified NSO image without compiling a duplicate flat table.

**Architecture:** A small C iterator accepts validated relocation table offsets and bounds, emits the same `where/kind/symbol/addend` tuples as the Python preflight, and refuses source tables overlapping writable data. Existing game loaders remain unchanged. A C harness runs synthetic and real offline comparisons from external temporary directories.

**Tech Stack:** C11, Python unittest, existing `game_tools/runtime_preflight.py`.

**Spec:** `docs/superpowers/specs/2026-10-23-direct-relocation-stream.md`

## Global Constraints

- Generated binaries, extracted NSOs, rewritten images, and benchmark logs stay outside every source worktree.
- No change to a shipped game loader or per-frame path in this phase.
- A successful iterator scan is static evidence only; startup and frame performance remain unassessed.

## Review Focus

- Source tables in writable data must be rejected before a callback can mutate them.
- RELR bitmap entries and implicit addends must match the Python decoder.
- Unsupported relocation kinds, out-of-range symbols and targets must fail closed.
- Callback termination must not continue to later records.
- Real Mario counts must match the existing Python preflight for `main` and `sdk`.

---

### Task 1: Relocation iterator

**Files:** Create `runtime_common/reloc_stream.h`, `runtime_common/reloc_stream.c`; test `tests/test_reloc_stream.py`.

**Interfaces:** `mng_reloc_walk(image, image_size, layout, visit, context, count)` emits `MngReloc` records; zero means success, nonzero means a format, bounds, or visitor failure.

- [x] Write synthetic tests for RELR, RELA, PLT, invalid spans/kinds and callback termination.
- [x] Run them and confirm failure before implementation.
- [x] Implement the bounded C iterator with immutable source table requirement.
- [x] Run focused and full suites.

### Task 2: Real input equivalence and cost record

**Files:** Create `tests/reloc_stream_probe.c`; update `docs/mario-wonder-input-probe.md`, `docs/generic-input-matrix.md`.

- [x] Compile the probe to a project-external temporary directory.
- [x] Rebuild Mario base ExeFS/rewrite/preflight outside the project, compare C counts, kind distribution and tuple checksum to Python output, and record a small proof.
- [x] Remove large temporary outputs; record source table bytes, potential duplicate bytes, and bounded traversal time without claiming gameplay performance.
- [x] Run full tests, review diff, commit.
