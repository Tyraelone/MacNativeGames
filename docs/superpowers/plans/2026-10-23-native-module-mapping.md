# Native Module Mapping Implementation Plan

**Goal:** Load compact-descriptor images into macOS memory with digest verification and safe final page permissions.

**Architecture:** A platform-specific mapper owns anonymous memory, reads a regular image file, hashes mapped bytes, then leaves data writable for the existing common linker. After all modules link, a sealing API applies RX/R/RW regions and invalidates instruction cache. A probe compares full linked images against the independent Python writer using actual mmap base addresses.

**Constraints:** Keep all generated inputs, binaries and proofs outside every source worktree. Existing game loaders remain unchanged. No guest entrypoint or constructor execution. Fail closed on any hash, layout, permission or linkage mismatch.

## Task 1: Mapper and synthetic tests

- [x] Write failing Mac-only tests for hash, size, symlink, seal readiness and page permissions.
- [x] Implement map/seal/unmap with no persistent file handle and no W+X pages.
- [x] Run focused tests.

## Task 2: Mario end-to-end proof

- [x] Build an external descriptor-driven map/link/seal probe and independent Python comparison.
- [x] Rebuild real Mario input outside source, record compact proof and clean large outputs.
- [x] Run full tests, review, resolve material findings, commit.
