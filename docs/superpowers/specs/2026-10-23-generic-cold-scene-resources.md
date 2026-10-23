# Generic cold-scene resource preparation

## Goal

Reduce the first visible frame cost when a newly packaged NVN game enters an unvisited scene. The mechanism must live in the shared NVN→Metal runtime; a game-specific texture list is not acceptable.

## Evidence and constraints

The Mario Wonder isolated route enters a new scene with 95–103 first-use textures. With shaders and pipelines already warm, one repeat takes 72.7 ms on frame 1290, of which 70.7 ms is submission and only 7.4 ms is measured texture upload. The GPU needs 6.5 ms. Thus shader compilation and GPU execution do not explain the remaining stall. Logs and repeatable input are stored under `/Users/duanziyu/Downloads/MarioWonder_build/logs/`; test profiles are under the user-data `tests` directory.

Texture data is mutable guest memory. Preparing an object early is safe only if the actual upload still reads the current bytes, keeps dirty generation checks, and obeys existing GPU queue/fence ordering. A bounded resource cache is required; preparing every descriptor indefinitely is not acceptable. Runtime memory safety and the residency-set guard remain active.

## Design

1. Attribute cold submission time among texture allocation/view resolution, upload, render-pass setup, argument encoding, and residency commits using opt-in per-frame counters. Do not infer a fix from `@upload_ms` alone.
2. Prepare the cache's shader-variant index and source-validity map on the existing warm worker before play, within index and source-read budgets. The runtime keeps lazy lookup for missing or later translated variants. Batch first-use memory-pool residency until the next GPU command-buffer commit, preserving ordering for uploads and draws.
3. Keep opt-out A/B controls. Check the same isolated route, screen image, GPU errors, memory, and frame metrics before installing the build. Texture allocation preparation is a possible follow-up only after measuring whether descriptors exist early enough to move the work without keeping stale guest pixels or unbounded resources.

## Acceptance

- A replay shows variant lookup moves off the scene-entry submit thread; the lazy path remains available when metadata preparation is disabled. GPU probes check resource lifetime, argument state, upload ordering, and vertex streams after residency batching.
- A first-scene A/B uses identical save, input, graphics configuration and warmed shader cache. Report entry frame time, submission CPU, new shader/pipeline count, first uploads, and memory. Keep the full TSV/log outside the source tree.
- The generic path does not add a significant sustained-frame regression or unbounded memory growth. If an unrecorded shader variant is created at runtime, report that limitation separately.
