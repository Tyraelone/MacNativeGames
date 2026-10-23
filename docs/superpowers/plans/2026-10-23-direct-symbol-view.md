# Direct Symbol View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read verified NSO dynamic symbols and names directly from image bytes while preserving current loader lookup semantics.

**Architecture:** Add a bounded C view over image resident symbol/string tables and a caller owned index of symbol numbers. Keep the existing game loader unchanged. Compare against Python preflight and the old loader's lookup rule offline.

**Tech Stack:** C11, Python unittest, existing runtime preflight and Mario base sample.

**Spec:** `docs/superpowers/specs/2026-10-23-direct-symbol-view.md`

## Global Constraints

- Generated binaries, rewritten images and benchmark logs stay outside the repository.
- Reject source tables overlapping writable data before any relocation write can occur.
- Preserve first defined duplicate name, including an invalid first value that masks a later valid one.
- No App or frame performance claim from an offline microbenchmark.

## Review Focus

- Bounds and NUL termination must be checked before any string operation.
- Symbol 0 must not enter the export hash even if marked defined.
- Hash capacity and allocation arithmetic must be bounded.
- Python and C names must have identical byte semantics.

### Task 1: View and index

**Files:** `runtime_common/symbol_view.{h,c}`, `tests/symbol_view_case.c`, `tests/test_symbol_view.py`, `game_tools/runtime_preflight.py`, `tests/test_runtime_preflight.py`.

- [x] Write failing synthetic C cases and a failing UTF-8 preflight case.
- [x] Implement bounded zero-copy symbol access and caller-owned index.
- [x] Run focused and full tests.

### Task 2: Real sample and record

**Files:** `tests/symbol_view_probe.c`, `game_tools/verify_symbol_view.py`, `docs/mario-wonder-input-probe.md`, `docs/generic-input-matrix.md`.

- [x] Rebuild the verified Mario base tables outside the repository.
- [x] Compare every C symbol row and distinct definition lookup against Python.
- [x] Keep the comparison as a repeatable external-only command, with patched-image hash checks.
- [x] Record allocation and microbenchmark cost in a small proof, then clean large temporary outputs.
- [x] Review, verify and commit.
