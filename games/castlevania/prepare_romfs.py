#!/usr/bin/env python3
"""Create the native read-only RomFS index outside the source checkout."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--romfs', type=Path, required=True, help='Verified merged RomFS directory')
parser.add_argument('--output', type=Path, required=True, help='External native host build directory')
args = parser.parse_args()
romfs = args.romfs.resolve()
output = args.output.resolve()
if romfs.is_relative_to(PROJECT) or output.is_relative_to(PROJECT):
    parser.error('Game data and generated tables must stay outside the source checkout')
manifest = json.loads((romfs / 'index.json').read_text())
if manifest.get('status') != 'pass' or (romfs / 'romfs.bin').stat().st_size != manifest['romfs_size']:
    raise ValueError('RomFS manifest or size mismatch')
strings = bytearray()
rows = bytearray()
previous = None
for item in sorted(manifest['files'], key=lambda row: row['path']):
    name = item['path'].encode() + b'\0'
    if previous is not None and name <= previous:
        raise ValueError('duplicate or unsorted RomFS path')
    if item['offset'] < 0 or item['size'] < 0 or item['offset'] + item['size'] > manifest['romfs_size']:
        raise ValueError('RomFS file bounds')
    rows.extend(struct.pack('<QQII', item['offset'], item['size'], len(strings), len(name)))
    strings.extend(name)
    previous = name
index = struct.pack('<8sQQ', b'TOTKRFS1', len(manifest['files']), 24 + len(rows)) + rows + strings
output.mkdir(parents=True, exist_ok=True)
(romfs / 'runtime-index.bin').write_bytes(index)
(output / 'romfs_config.h').write_text(
    f'#define ROMFS_IMAGE_SIZE {manifest["romfs_size"]}ULL\n'
    f'#define ROMFS_IMAGE_SHA256 "{manifest["romfs_sha256"]}"\n'
    f'#define ROMFS_INDEX_SHA256 "{hashlib.sha256(index).hexdigest()}"\n'
)
print(json.dumps({'files': len(manifest['files']), 'index_bytes': len(index),
                  'index_sha256': hashlib.sha256(index).hexdigest()}))
