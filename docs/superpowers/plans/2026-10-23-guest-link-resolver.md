# Guest Link Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the common image symbol view can resolve actual guest module relocations with current loader precedence.

**Architecture:** A small C resolver uses caller supplied module views, load order, bases and optional host callback. It plugs into `mng_reloc_apply`. A reproducible external-only verifier compares complete relocated image hashes against an independent Python flat-table writer.

**Tech Stack:** C11, Python unittest and verified Mario preflight data.

**Spec:** `docs/superpowers/specs/2026-10-23-guest-link-resolver.md`

## Constraints

- No generated image, binary, TSV, test save or cache in the source checkout.
- No existing game loader or per-frame path change.
- Host callback resolution is an interface only, not a claim of host ABI support.
- A partially relocated image after an error must be discarded.

### Task 1: Resolver core

**Files:** `runtime_common/guest_link.{h,c}`, `tests/guest_link_case.c`, `tests/test_guest_link.py`.

- [x] Write failing synthetic precedence and failure tests.
- [x] Implement module, weak and optional host resolution with address bounds.
- [x] Run focused and full tests.

### Task 2: Real module application

**Files:** `tests/guest_link_probe.c`, `game_tools/verify_guest_link.py`, sample docs.

- [x] Rebuild verified Mario base inputs outside the repository.
- [x] Compare C applied image hashes and category counts to independent Python flat-table application.
- [x] Record startup-only cost, clean large outputs and keep a small proof.
- [x] Review, verify and commit.
