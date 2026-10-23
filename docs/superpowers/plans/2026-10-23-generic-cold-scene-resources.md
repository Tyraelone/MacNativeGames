# Generic cold-scene resource plan

Spec: `../specs/2026-10-23-generic-cold-scene-resources.md`

1. Add opt-in per-frame timing for the shared NVN→Metal cold path. Build the native host externally, replay the isolated Mario route, and record which category explains the shader-warm scene-entry stall. The timing mode must be off by default.
2. Implement the shared-runtime preparation or batching change indicated by the measurements. Check a failing isolated replay first, then verify the candidate. Keep explicit byte and work budgets where preparation scans cache data, plus the existing synchronous fallback.
3. Rebuild outside the source checkout. Run the new probe, all relevant unit tests, and the same scene route with control and candidate binaries. Compare image, shader/Pipeline counts, entry frame and steady-frame metrics, GPU errors, and memory. Package/install only a verified candidate; document limits and evidence paths.
