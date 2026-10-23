# Descriptor-Driven Link Implementation Plan

**Goal:** Link verified guest modules directly from compact descriptors without duplicate symbol or relocation rows.

**Architecture:** Extend descriptor validation to return an open symbol view. A caller-owned module context builds its symbol index once, then a common link function wires all contexts into the existing guest resolver and relocation writer. An external verifier compares real Mario linked images to the independent Python writer.

**Constraints:** Keep all generated images, headers, probes and proof outside every source worktree. Do not switch existing game loaders. Require caller-side mapped-image SHA-256 verification before prepare.

## Task 1: Bounded link API

- [x] Write a failing C case for prepare/link success and failure boundaries.
- [x] Implement descriptor open plus caller-owned link context and workspace.
- [x] Run focused tests.

## Task 2: Real descriptor-driven proof

- [x] Build an external verifier that emits a descriptor, compiles the probe and compares whole linked images to Python.
- [x] Rebuild Mario base input outside the project and record a small proof.
- [x] Run full tests, read-only review, fix findings, and commit.

Review found no blocking defect. Deferred minor follow-up: add an orchestration-level host-versus-guest precedence case. The public header now spells out retained descriptor/source/index lifetimes.
