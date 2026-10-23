# Compact Runtime Descriptor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit compact C module metadata from verified generic preflight without a duplicate symbol or relocation table.

**Architecture:** Define a common descriptor structure and bounded C pre-use validator. A build-time generator reads external runtime preflight tables, verifies rewrite hashes, and writes one external header. A C probe compiled against that header validates the real Mario source tables and reports metadata for Python comparison.

**Tech Stack:** Python standard library, C11, existing runtime common symbol/relocation readers.

**Spec:** `docs/superpowers/specs/2026-10-23-compact-runtime-descriptor.md`

## Constraints

- No generated header, images, binary or proof inside any source worktree.
- Existing game loaders and frame paths retain their current behavior.
- Descriptor digest is metadata; a future loader must independently hash mapped bytes.
- Do not infer constructor behavior or host service compatibility.

### Task 1: Format and generator

**Files:** `runtime_common/module_descriptor.{h,c}`, `game_tools/emit_runtime_descriptor.py`, `tests/test_runtime_preflight.py`.

- [x] Write failing synthetic generation and C validation cases.
- [x] Implement the bounded descriptor format and generator with external path/hash checks.
- [x] Run focused and full tests.

### Task 2: Real input proof

**Files:** `tests/module_descriptor_probe.c`, sample docs.

- [x] Rebuild Mario base rewrite/preflight outside the repository.
- [x] Compile the emitted descriptor with a C consumer, compare counts/layout/gates to Python and record size.
- [x] Clean large generated data, review, verify and commit.
