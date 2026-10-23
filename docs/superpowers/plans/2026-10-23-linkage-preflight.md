# Linkage Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify the symbols actually referenced by relocation rows using the existing module lookup order.

**Architecture:** Add a pure analyzer to `runtime_preflight.py`, then include its output in the external runtime summary. No host registry or runtime loader changes.

**Tech Stack:** Python standard library and unittest.

**Spec:** `docs/superpowers/specs/2026-10-23-linkage-preflight.md`

## Global Constraints

- The input is the hash-verified, parsed module set already produced by `runtime_preflight.py`.
- A module definition is only a candidate; host overrides and ABI compatibility are not established.
- Full tables and generated data stay outside the source checkout.
- Runtime and frame paths remain unchanged.

## Review Focus

- Unreferenced imports must not count as load blockers.
- A local nonweak definition takes precedence over a global candidate.
- A weak symbol without guest definition may become zero, not a proven host implementation.
- A strong symbol without guest definition is only a potential host requirement because overrides are unknown.
- The excluded `rtld` must not satisfy candidate lookup.
- Reserved dynamic symbol index zero must not enter the loader's export hash.

---

### Task 1: Pure linkage analyzer

**Files:** Modify `game_tools/runtime_preflight.py`, `tests/test_runtime_preflight.py`.

**Interfaces:** `summarize_linkage(modules, module_order)` returns a per-module diagnostic dictionary.

- [x] Write a failing synthetic test for local/global/weak/host classes and unreferenced imports.
- [x] Implement candidate lookup and counts without copying the relocation list.
- [x] Add the diagnostic to the external `runtime-summary.json` and exercise it through `prepare`.
- [x] Run focused and full tests.

### Task 2: Real sample and record

**Files:** Update `docs/mario-wonder-input-probe.md`, `docs/generic-input-matrix.md`, `README.md`.

- [x] Rebuild only Mario's verified ExeFS rewrite and preflight in an external temporary directory.
- [x] Record referenced-symbol categories and unique names in a small proof, with explicit host limitations.
- [x] Clean temporary tables, review the diff and commit.
