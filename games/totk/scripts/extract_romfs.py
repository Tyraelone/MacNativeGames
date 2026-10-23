#!/usr/bin/env python3
"""Compatibility entry for the shared RomFS extractor and indexer."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
script = Path(__file__).resolve()
root = next((base for base in (script.parents[2], script.parents[3])
             if (base / 'game_tools/__init__.py').is_file()), None)
if root is None:
    raise ModuleNotFoundError('game_tools is missing from the build work folder')
sys.path.insert(0, str(root))
from game_tools.extract_romfs import *  # noqa: F401,F403
from game_tools.extract_romfs import main as _shared_main


def main():
    return _shared_main(
        default_manifest=Path('extracted/v0/extraction-manifest.json'),
        default_output=Path('extracted/v0/romfs'),
        default_title_id='0100F2C0115B6000',
    )


if __name__ == "__main__":
    main()
