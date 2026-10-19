# Kirby Star Allies 4.1.0 experimental profile

This directory is for the experimental native port of **Kirby Star Allies 4.1.0**
(`01007E3006DDA000`). The current runtime reaches the title, file selection,
story menu, movable world map, and the first level. Movement, jumping, and an
action were verified inside that level. The experimental app uses a simplified
scene and sky composite to avoid severe 3D postprocessing artifacts. Original
lighting and extended play have not been verified. See
[`docs/kirby-experiment.md`](../../docs/kirby-experiment.md) for evidence and
reproduction commands.

## Run

The experimental app is stored outside the source tree at
`/Users/duanziyu/Documents/deepseek-harness/kirby-work/Kirby Star Allies (Experimental).app`.
Open it, press **J** for Switch A to pass the title and enter a level, and use
**WASD** to move. **K** or Space is Switch B. The app creates its own save under
`~/Library/Application Support/MacNativeGames/Kirby`.

## Save import from Ryujinx

The native runtime can now pass the opening movie and create its own save. If you
want to import an existing Ryujinx/Ryubing save instead, use:

```sh
python3 games/kirby/tools/import_ryujinx_save.py \
  --ryujinx-save "$HOME/Library/Application Support/Ryujinx/bis/user/save" \
  --profile /path/to/kirby-work/profile
```

The tool finds the `01007E3006DDA000` save directory, backs up the existing native
save, and copies the files into the profile's single save slot. It does not modify
Ryujinx's save. The native profile must already contain one save slot (created by
starting the experimental runtime once).

Ryujinx's macOS save root is normally:

```text
~/Library/Application Support/Ryujinx/bis/user/save/0000000000000000/01007E3006DDA000
```

If the emulator uses a different user id, pass its `bis/user/save` root and let the
tool search for the title id.

## Boundary

No game data, keys, firmware or saves are stored in this repository. The tool only
copies files the user already owns.
