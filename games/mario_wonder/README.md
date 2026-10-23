# Super Mario Bros. Wonder native preview

This target packages the verified 1.2.1 update into a standalone macOS App. It
uses the shared NSO rewrite/preflight/RomFS tooling and the current native host.
The runtime service and NVN changes in this repository were exercised through
the title menu, account and character selection, opening sequence, and initial
playable scene. This is a preview, not a claim that the complete game has been
verified.

The builder requires an **external** `MarioWonder_build` work directory already
containing:

- `update/control.nacp` from the user's update, with display version `1.2.1`;
- verified merged `update/romfs` and `update/packed-rewrites/{main,sdk}.patched.bin`;
- `native-host` with `build/runtime_tables.h`, `build/romfs_config.h`,
  `build/shared_fonts_config.h`, the six shared fonts, the native shader
  translator, `spirv-cross`, and `build/local-avatar.jpg`.

For the current machine, the build is:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 games/mario_wonder/build_app.py \
  --work ~/Downloads/MarioWonder_build \
  --output '~/Downloads/MarioWonder_build/apps/Super Mario Bros. Wonder Native Preview.app'
```

The script expands `~` in path arguments. It refuses output inside the
source tree and refuses to overwrite an App. It syncs the tracked native
changes into the external build host, compiles the Mario variant, copies
resources into the App, builds the icon from the update control asset, and
ad-hoc signs the bundle. NSPs and `prod.keys` are not placed in the App.

For a performance build, add `--recorded-cache` with an external shader cache
collected during play. The builder exports only complete variants matching the
native translation chain, compiles their Metal libraries with the renderer's
safe-math setting, and includes the observed pipeline warm-up list. It checks
file hashes before packaging and keys reuse to every shader input, so a cache
change cannot silently reuse an older seed. Profile, save, account ID, and
other personal files are excluded. The source cache and all generated seeds,
libraries, and Apps stay outside this repository.

To prepare the finite set embedded in this version's game assets, run the
offline scanner against the verified RomFS. It finds BNSH programs inside
Shader, Effect, and Layout assets and translates their default bound-state
variants before packaging:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 games/mario_wonder/prepare_static_shader_seed.py \
  --romfs ~/Downloads/MarioWonder_build/update/romfs \
  --translator ~/Downloads/MarioWonder_build/native-host/build/shader-service/totk_xlate \
  --spirv-cross ~/Downloads/MarioWonder_build/native-host/build/spirv-cross/spirv-cross \
  --output ~/Downloads/MarioWonder_build/development/static-shader-seed
```

Add `--static-seed` when building the App. Multiple `--recorded-cache` arguments
can combine separate test routes; their exact variants take priority over the
static defaults. The builder verifies that the static seed came from the same
RomFS, merges variant indexes, includes observed render and compute pipelines,
and precompiles distinct Metal libraries. The startup loading screen waits for
the bundled list to finish warming before presenting the title. A shader's
runtime variant can still depend on vertex attributes, texture types, or render
target state, and unseen pipeline combinations cannot be enumerated from the
static assets alone.

The App keeps profile, saves, shader cache, and RomFS verification state in
`~/Library/Application Support/MacNativeGames/MarioWonder`; logs go to
`~/Library/Logs/MacNativeGames`. Isolated validation used the separate
`MarioWonder/tests/bootstrap-20261023` subtree. The App does not use the
existing Tears of the Kingdom desktop entry or save directory.

On a Mac keyboard, Q and E represent L/R pairing at the title screen;
A/D move, J confirms or jumps, and K returns. A controller can also be used
through the native GameController host. The renderer and audio exercised in
the opening scene; complete game coverage and audio effect type 6 remain open.

Local evidence remains outside the repository. The interactive test log is
`/Users/duanziyu/Downloads/MarioWonder_build/logs/mario-boot-30.log`; its last
300-frame opening-scene window recorded 8.33 ms median and 8.64 ms p95 frame
time at a 120 Hz display, with 5.83 ms GPU p95. The gameplay screenshot is
`logs/mario-preview-30g.png` there. The signed App's Finder-launched title
screen after the review fixes is `logs/mario-packaged-final.png`. These measurements cover a short
scene on one Mac, so they do not establish sustained or whole-game performance.

On 2026-10-23, an isolated movement test traced severe first-use Metal shader
and pipeline creation on the submit thread. The recorded user and isolated
gameplay caches yielded 1,193 complete variants and 1,160 distinct precompiled
Metal libraries. The fully drawn optimized candidate, tested with a copied
profile and a new cache, recorded 953 consecutive movement frames (8000–8952)
in `logs/mario-perf-optimized.tsv`: p99 8.80 ms, maximum 13.52 ms, zero new
pipelines in that window. The corresponding game log and screenshot are
`logs/mario-perf-optimized.log` and `logs/mario-perf-optimized-moving.png`.
The test data is under the user's `MarioWonder/tests/perf-optimized-20261023`
directory; the normal save was not used for test writes. Scene transitions in
this test still had some first-use pipelines, and unvisited content is not
covered by the recorded seed. An asynchronous compile experiment eliminated
movement pauses but skipped thousands of draws during scene loading, so the
packaged App retains complete synchronous drawing.

The final signed bundle is recorded in
`/Users/duanziyu/Downloads/MarioWonder_build/logs/mario-optimized-final-build.log`:
1,193 variants, 1,160 distinct precompiled libraries, and 2,229 warmed
pipelines. A fresh isolated cache imported the bundled seed and ran 1,137
movement frames (10200–11336) in `logs/mario-perf-final.tsv` with p99 12.01 ms,
maximum 18.60 ms, and zero new pipelines. The game log and complete gameplay
image are `logs/mario-perf-final.log` and `logs/mario-perf-final-moving.png`.
During that same run, entry into an unrecorded scene still took 477.9 ms on
frame 1441 while compiling one new shader library and pipeline. The seed
addresses the recorded routes; first visits elsewhere still need broader
preparation before a whole-game smoothness claim is justified.

The broader 2026-10-23 prewarm build is preserved at
`/Users/duanziyu/Downloads/MarioWonder_build/apps/Super Mario Bros. Wonder Native Preview.app`.
The later cold-scene runtime build is packaged at
`/Users/duanziyu/Downloads/MarioWonder_build/apps/Super Mario Bros. Wonder Native Cold Scene.app`
and installed at `/Applications/超级马里奥兄弟 惊奇.app`.
The Applications copy passed deep code-signature verification. Its verified
merged RomFS, rewritten executables, and shader seed match the previous
standalone build byte for byte; only the native host binary changed.
The previous installed App is preserved in
`development/previous-mario-preview-before-cold-scene-20261023.app`.
The preceding recorded-seed build is preserved in
`development/previous-mario-preview-recorded-20261023.app` there.
Its seed combines 6,813 static defaults with the recorded routes for 8,007
variants, 7,174 distinct precompiled libraries, and 2,321 observed pipelines.
The isolated cold test is `logs/mario-perf-static-warm.log` with profile/cache
under `MarioWonder/tests/perf-static-warm-20261023`. First launch spent about
11 seconds importing 23,142 seed files and 14.2 seconds warming; a later launch
reused the import and warmed in 8.8 seconds (`logs/mario-perf-static-warm-second-fixed.log`).
The previously 477.9 ms scene-entry frame became 73.1 ms, with no new shader or
pipeline; it still uploaded 95 textures. A genuinely held movement interval of
1,041 frames (7400–8440) measured p99 11.88 ms and maximum 15.78 ms, with
zero new pipelines. Its complete gameplay image is
`logs/mario-perf-static-warm-held.png`. Other first-use stalls can come from
texture uploads, game logic, or runtime shader states not represented by the
default and recorded variants; this is not full-game coverage.

### Remaining scene-entry stutter

In the same isolated run, frame 1971 spent 73.1 ms overall and 70.8 ms in
submission/presentation, while the GPU spent 7.4 ms. There were no new shader
libraries or pipelines. The frame first uploaded 95 textures (7.0 MB), with
9.7 ms measured inside the texture upload path. Submission used 52.4 ms of
thread CPU time and about 604 million instructions; the held movement window
(frames 7400–8440) had submission CPU and instruction medians of 1.7 ms and
9.8 million despite a similar draw count. Frame 3072 shows a second example:
83.3 ms overall, 77.3 ms submission/presentation, 7.6 ms GPU, 62 first
uploads (51.0 MB, 10.4 ms upload path), and no new shader or pipeline. Evidence:
`/Users/duanziyu/Downloads/MarioWonder_build/logs/mario-perf-static-warm.tsv`
and the corresponding `.log` in the same external directory.

The shared-runtime cold-scene pass measured that 51.8 ms of a 74.8 ms entry
frame came from resolving cached shader variants: the submit thread parsed
individual `.variants` files and checked Metal source even though their
libraries and pipelines were already warm. The warm worker now prepares this
mapping before releasing the loading screen, with 16 MiB of index data and
512 MiB of source reads as startup budgets. On this build it checked 8,007
variants in 7,127 indexes, reading 205.3 MiB of source in 4.4–5.7 seconds.
The original lazy path remains for variants beyond the budget and variants
translated after warm-up. `TOTK_RT_META_PREWARM=0` is an A/B control.

The same first scene made 35 new memory pools resident and committed the
Metal residency set 39 times. The shared runtime now batches first-use pool
registration until the next GPU command-buffer commit, which preserved GPU
ordering in four resource-lifetime/upload probes and reduced actual commits
to five on the measured frame. `TOTK_POOL_RES_BATCH=0` is the control.
Both changes apply to every game built with this NVN→Metal host, without a
game-specific texture list or cached guest pixels.

In an isolated copy of the save, with identical scripted input and warmed
shader cache, the control build with both switches off took 81.8 ms on the
99-texture entry frame (53.4 ms submit CPU, 642.6 million submit instructions,
zero new pipelines); the candidate with both on took 30.8 ms on its
103-texture entry frame (27.3 ms submit CPU, 151.4 million instructions,
zero new pipelines). The final standalone App took 34.3 ms on its 98-texture
entry frame and rendered the expected playable scene. Evidence is outside
the source tree under `logs/mario-generic-{control-clean,candidate-clean,packaged-final}.{log,tsv}`
and `logs/mario-generic-packaged-final.png` in `MarioWonder_build`. The copied
test save and shader cache are under the user's `MarioWonder/tests/generic-coldpath-repro-20261023`
directory. The normal save was not used for writes. Over the next 300 frames,
the control and candidate medians were both about 8.34 ms; their p95 values
were 10.41 and 8.85 ms, respectively. The recorded maximum GPU allocations
were 1,260 and 1,280 MiB, without an observed growth trend in this short run.

The measured first entry is much shorter but still exceeds a 16.7 ms frame
budget, and unrelated game-logic spikes and previously unseen shader states
remain possible. The next generic step is bounded preparation of texture
allocations during scene loading when descriptors and guest memory actually
exist; it must retain generation checks, resource retirement, and a synchronous
fallback. This build does not promise a stutter-free first visit to every scene.
