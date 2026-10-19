# Kirby Star Allies 4.1.0 experimental profile

This directory is for the experimental native port of **Kirby Star Allies 4.1.0**
(`01007E3006DDA000`). It is not a supported release and it does not make the game
playable by itself. The current runtime reaches the first submitted frame and then
stops in `Movie.Scene` with a Mint VM exception; see
[`docs/kirby-experiment.md`](../../docs/kirby-experiment.md) for the full status,
evidence and commands.

## Save import from Ryujinx

The opening movie is the current blocker. A save that has already watched the
movie can be produced with a general Switch emulator (Ryujinx/Ryubing) and then
imported into the native profile:

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
