# Relocation Apply Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply verified NSO relocations directly from source tables and compare their effects and offline cost with a flat-table baseline.

**Architecture:** A small C apply function visits the existing stream and delegates symbolic addresses to a caller callback. Tests cover writes and failure behavior; an external-data probe compares complete writable-region hashes with an independent flat loop.

**Tech Stack:** C11, Python unittest, existing `runtime_common/reloc_stream.c` and `game_tools/runtime_preflight.py`.

**Spec:** `docs/superpowers/specs/2026-10-23-relocation-apply-core.md`

## Global Constraints

- Inputs have passed offline hash and structure preflight; duplicate relocation targets are rejected there.
- Source tables must precede writable data, so writes cannot change unread relocation records.
- Generated binaries, rewritten images, flat arrays and benchmark work remain outside the source checkout.
- Current title-specific loaders and frame/render paths do not change.

## Review Focus

- `JUMP_SLOT` ignores the stored addend exactly as the existing loader does.
- RELR reads its implicit addend before the target is overwritten.
- A source-table overlap fails before any target is written.
- A resolver failure stops before writing its target or later targets.
- Synthetic addresses are never described as real host bindings.

---

### Task 1: Core semantics

**Files:** Create `runtime_common/reloc_apply.h`, `runtime_common/reloc_apply.c`, `tests/reloc_apply_case.c`, `tests/test_reloc_apply.py`.

**Interfaces:** `mng_reloc_apply(image, image_size, layout, base, resolve, context, count)` returns an existing relocation status or a resolution error; `resolve(context, symbol_index, kind, &value)` produces the symbol address.

- [x] Write synthetic tests for four kinds, RELR implicit addends, source overlap and resolver failure.
- [x] Run tests and confirm failure before implementation.
- [x] Implement the minimal apply callback over `mng_reloc_walk`.
- [x] Run focused and full suites.

### Task 2: Real input equivalence and cost

**Files:** Create `tests/reloc_apply_probe.c`; update `docs/mario-wonder-input-probe.md`, `docs/generic-input-matrix.md`, `README.md`.

- [x] Rebuild Mario base ExeFS and verified rewritten `main/sdk` in an external temporary directory.
- [x] Compare stream and independent flat writes over all relocation targets with deterministic test symbol addresses; record full writable-region hashes and timed rounds.
- [x] Remove large outputs and retain only a small proof with clear runtime limitations.
- [x] Run full tests, review and commit.
