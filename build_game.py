#!/usr/bin/env python3
"""One entry for the project's verified Mac build and packaging workflows."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TARGETS = {
    "totk": (
        "0100F2C0115B6000",
        "full build from verified XCI/NSP",
        ROOT / "build_app.py",
        ROOT / "games/totk/assets",
    ),
    "kirby-preview": (
        "01007E3006DDA000",
        "preview packaging from a prepared host",
        ROOT / "games/kirby/package_preview.py",
        ROOT / "games/kirby/assets",
    ),
    "castlevania": (
        "0100BA4026E94000",
        "1.1.0 packaging from verified work",
        ROOT / "games/castlevania/build_app.py",
        ROOT / "games/castlevania/assets",
    ),
}


def usage() -> str:
    return (
        "Usage: python3 build_game.py list\n"
        "       python3 build_game.py inspect <game.xci|game.nsp> --keys <prod.keys> [--title-id HEX]\n"
        "       python3 build_game.py <target> <existing builder arguments>\n\n"
        "Targets:\n"
        + "".join(f"  {name:<16} {details[1]}\n" for name, details in TARGETS.items())
        + "\nUse '<target> --help' for that builder's options. "
        "Unknown games and versions are unsupported.\n"
    )


def command_for(target: str, arguments: list[str]) -> list[str]:
    script = ROOT / "inspect_game.py" if target == "inspect" else TARGETS[target][2]
    return [sys.executable, str(script), *arguments]


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["list"]:
        for name, (title_id, status, _, _) in TARGETS.items():
            print(f"{name:<16} {title_id}  {status}")
        return 0
    if args in (["--help"], ["-h"]):
        print(usage(), end="")
        return 0
    if not args or args[0] not in TARGETS and args[0] != "inspect":
        print(f"Unknown target: {args[0] if args else '(none)'}\n{usage()}", file=sys.stderr, end="")
        return 2
    result = subprocess.run(command_for(args[0], args[1:]), check=False)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
