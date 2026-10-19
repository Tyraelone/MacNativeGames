#!/usr/bin/env python3
"""Import a Ryujinx Kirby Star Allies save into the experimental native profile."""
import argparse, shutil, sys
from pathlib import Path
TITLE = '01007E3006DDA000'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ryujinx-save', type=Path, required=True,
                    help='Ryujinx save directory for %s (or its bis/user/save root)' % TITLE)
    ap.add_argument('--profile', type=Path, default=Path('profile'),
                    help='native runtime profile directory (default: ./profile)')
    args = ap.parse_args()
    root = args.ryujinx_save.expanduser()
    if (root / TITLE).is_dir():
        source = root / TITLE
    elif root.name == TITLE and root.is_dir():
        source = root
    else:
        found = [p for p in root.rglob(TITLE) if p.is_dir()]
        if not found:
            sys.exit(f'no {TITLE} save directory under {root}')
        source = found[0]
    saves = [p for p in (args.profile / 'save').iterdir() if p.is_dir()] if (args.profile / 'save').is_dir() else []
    if len(saves) != 1:
        sys.exit(f'expected exactly one native save dir under {args.profile}/save, found {len(saves)}')
    dest = saves[0]
    backup = dest.with_name(dest.name + '-before-ryujinx')
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(dest, backup)
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, dest / item.name)
            print(f'copied {item.name} ({item.stat().st_size} bytes)')
    print(f'source: {source}')
    print(f'destination: {dest}')
    print(f'backup: {backup}')

if __name__ == '__main__':
    main()
