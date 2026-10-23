#!/usr/bin/env python3
"""Compatibility entry for the shared BKTR RomFS merger."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
script = Path(__file__).resolve()
root = next((base for base in (script.parents[2], script.parents[3])
             if (base / 'game_tools/__init__.py').is_file()), None)
if root is None:
    raise ModuleNotFoundError('game_tools is missing from the build work folder')
sys.path.insert(0, str(root))
from game_tools.extract_update_romfs import *  # noqa: F401,F403
from game_tools.extract_update_romfs import merge as _shared_merge, main as _shared_main


DEFAULT_TITLE_ID = '0100F2C0115B6000'


def merge(base, update, keys_path, hactool, output, *, base_romfs=None,
          title_id=DEFAULT_TITLE_ID):
    return _shared_merge(base, update, keys_path, hactool, output,
                         base_romfs=base_romfs, title_id=title_id)


def main():
    return _shared_main(default_title_id=DEFAULT_TITLE_ID)


if __name__ == '__main__':
    main()
