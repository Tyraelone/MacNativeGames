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
