#!/usr/bin/env python3
"""Generate native loader tables for verified Castlevania 1.1.0 modules.

All input images and generated tables live outside the source checkout.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'games/totk/third_party/d2r'))
from relr import decode_relr
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work', required=True, type=Path, help='External main/update directory')
parser.add_argument('--output', required=True, type=Path, help='External directory for runtime_tables.h and layout')
args = parser.parse_args()
WORK = args.work.resolve()
OUT = args.output.resolve()
if WORK.is_relative_to(PROJECT) or OUT.is_relative_to(PROJECT):
    parser.error('Game data and generated tables must stay outside the source checkout')
OUT.mkdir(parents=True, exist_ok=True)
REWRITES = {'main': WORK / 'rewritten-indirect', 'subsdk0': WORK / 'rewritten', 'sdk': WORK / 'rewritten'}
EXEFS = WORK / 'exefs'
ELF = WORK / 'elf'
EXPECTED_MAIN_BUILD_ID = '0f1169aa7d0fa4529c861f96adec306e' + '0' * 32
main_inventory = json.loads((ELF / 'main-inventory.json').read_text())
if main_inventory.get('build_id') != EXPECTED_MAIN_BUILD_ID:
    raise ValueError('Unsupported main build ID')
modules = []
for name in ['main', 'subsdk0', 'sdk']:
    path = REWRITES[name] / f'{name}.patched.bin'
    image = path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    inv = json.loads((ELF / f'{name}-inventory.json').read_text())
    layout = {}
    for line in (REWRITES[name] / f'{name}.fixups.tsv').read_text().splitlines():
        _, key, value = line.split()
        layout[key] = int(value, 0)
    mod0 = struct.unpack_from('<I', image, 4)[0]
    assert image[mod0:mod0 + 4] == b'MOD0'
    dyn = mod0 + struct.unpack_from('<i', image, mod0 + 4)[0]
    tags = {}
    for offset in range(dyn, dyn + 4096 * 16, 16):
        tag, value = struct.unpack_from('<qQ', image, offset)
        if tag == 0: break
        tags[tag] = value
    else: raise ValueError('Unterminated dynamic table')
    if 4 in tags:
        nsym = struct.unpack_from('<I', image, tags[4] + 4)[0]
    else:
        # Newer SDK modules carry GNU hash only. NSO's verified dynsym extent
        # supplies the exact count, as in prepare_modules.py's inventory gate.
        raw_header = (EXEFS / name).read_bytes()[:256]
        _, _, symbol_offset, symbol_size = struct.unpack_from('<IIII', raw_header, 0x90)
        assert layout['RO_OFF'] + symbol_offset == tags[6] and symbol_size % 24 == 0
        assert 0 < symbol_size <= layout['DATA_OFF'] - tags[6]
        nsym = symbol_size // 24
    assert tags[11] == 24 and tags[9] == 24 and tags[20] == 7
    symbols = []
    for i in range(nsym):
        no, info, other, section, value, size = struct.unpack_from('<IBBHQQ', image, tags[6] + 24 * i)
        end = image.index(0, tags[5] + no, tags[5] + tags[10])
        symbols.append(dict(name=image[tags[5] + no:end].decode(), value=value, size=size,
                            defined=bool(section), binding=info >> 4, type=info & 15))
    relocs = [dict(where=where, kind=1027, symbol=0, addend=addend)
              for where, addend in decode_relr(image, tags, layout['DATA_OFF'], layout['KEY_PAGE_OFF'])]
    relocated = {reloc['where'] for reloc in relocs}
    for address, size in [(tags[7], tags[8]), (tags[23], tags[2])]:
        assert size % 24 == 0
        for offset in range(address, address + size, 24):
            where, info, addend = struct.unpack_from('<QQq', image, offset)
            kind, si = info & 0xffffffff, info >> 32
            assert kind in [257, 1025, 1026, 1027] and si < nsym
            assert layout['DATA_OFF'] <= where <= layout['KEY_PAGE_OFF'] - 8
            assert kind != 1027 or 0 <= addend < layout['KEY_PAGE_OFF']
            assert where not in relocated, 'Duplicate RELR/RELA relocation'
            relocated.add(where)
            relocs.append(dict(where=where, kind=kind, symbol=si, addend=addend))
    gates = []
    for line in (REWRITES[name] / f'{name}.gates.tsv').read_text().splitlines():
        ret, kind, arg, original = line.split()
        assert kind in ['cntpct', 'cntvct', 'svc']
        gates.append(dict(ret=int(ret, 0), timer=kind != 'svc', arg=int(arg), original=int(original, 0)))
    # Match each compiler's actual DT_INIT state load before decoding it.
    flag_reg, load_offset = 19, 20
    a, w = struct.unpack_from('<I', image, tags[12]+16)[0], struct.unpack_from('<I', image, tags[12]+load_offset)[0]
    assert a & 0x9f00001f == 0x90000000 | flag_reg and w & 0xffc003ff == 0xb9400008 | (flag_reg << 5)
    imm = ((a >> 29) & 3) | (((a >> 5) & 0x7ffff) << 2)
    imm = (imm ^ (1 << 20)) - (1 << 20)
    ctor_flag = ((tags[12]+16) & ~4095) + (imm << 12) + ((w >> 10) & 0xfff)*4
    assert layout['DATA_OFF'] <= ctor_flag < layout['KEY_PAGE_OFF']
    modules.append(dict(name=name, sha256=digest, size=len(image), ctor_flag=ctor_flag, layout=layout, tags=tags,
                        symbols=symbols, relocs=relocs, gates=gates))

# Find main's ORIGINAL PLT stub addressing the relocated GetSystemTick slot.
main = modules[0]
target = '_ZN2nn2os13GetSystemTickEv'
slot = next(r['where'] for r in main['relocs'] if main['symbols'][r['symbol']]['name'] == target and r['kind'] == 1026)
image = (REWRITES['main'] / 'main.patched.bin').read_bytes()
plt = []
branch_x17 = struct.pack('<I', 0xd61f0220)
position = 0
while (position := image.find(branch_x17, position, main['layout']['TEXT_END'])) >= 0:
    address = position - 12
    position += 4
    if address < 0 or address % 4: continue
    a, b, c, d = struct.unpack_from('<IIII', image, address)
    if a & 0x9f00001f != 0x90000010 or b & 0xffc003ff != 0xf9400211 or d != 0xd61f0220: continue
    if c != 0x91000210 | (((b >> 10) & 0xfff) * 8 << 10): continue
    imm = ((a >> 29) & 3) | (((a >> 5) & 0x7ffff) << 2)
    imm = (imm ^ (1 << 20)) - (1 << 20)
    referenced = (address & ~4095) + (imm << 12) + ((b >> 10) & 0xfff) * 8
    if referenced == slot: plt.append(address)
assert len(plt) == 1, f'PLT matches {plt}, slot {slot:#x}'
main['probe_plt'] = plt[0]
main['probe_slot'] = slot

lines = ['/* Generated locally from validated player images; do not commit. */']
for n, m in enumerate(modules):
    lines.append(f'static const Reloc reloc_{n}[] = {{')
    lines.extend(f'{{{r["where"]}ULL,{r["kind"]},{r["symbol"]},{r["addend"]}LL}},' for r in m['relocs'])
    lines.append('};')
    lines.append(f'static const Symbol symbol_{n}[] = {{')
    lines.extend('{' + f'{json.dumps(s["name"])},{s["value"]}ULL,{s["size"]}ULL,{int(s["defined"])},{s["binding"]},{s["type"]}' + '},' for s in m['symbols'])
    lines.append('};')
    lines.append(f'static const Gate gate_{n}[] = {{')
    lines.extend(f'{{{g["ret"]}ULL,{g["original"]}ULL,{g["timer"]!s},{g["arg"]}}},'.replace('True','1').replace('False','0') for g in m['gates'])
    if not m['gates']: lines.append('{0,0,0,0},')
    lines.append('};')
lines.append('static Module modules[] = {')
for n, m in enumerate(modules):
    l = m['layout']
    lines.append('{' + f'.name={json.dumps(m["name"])},.digest={json.dumps(m["sha256"])},.file_size={m["size"]}ULL,.text_end={l["TEXT_END"]}ULL,.ro_off={l["RO_OFF"]}ULL,.data_off={l["DATA_OFF"]}ULL,.patch_off={l["PATCH_OFF"]}ULL,.key_off={l["KEY_PAGE_OFF"]}ULL,.symbols=symbol_{n},.nsym={len(m["symbols"])},.relocs=reloc_{n},.nreloc={len(m["relocs"])},.gates=gate_{n},.ngate={len(m["gates"])},.init={m["tags"].get(12,0)}ULL,.ctor_flag={m["ctor_flag"]}ULL,.init_array={m["tags"].get(25,0)}ULL,.init_size={m["tags"].get(27,0)}ULL' + '},')
lines.append('};')
lines.append(f'#define PROBE_PLT {main["probe_plt"]}ULL\n#define PROBE_SLOT {slot}ULL')
(OUT / 'runtime_tables.h').write_text('\n'.join(lines) + '\n')
# Details are evidence, not additional source code.
(OUT / 'runtime-layout.json').write_text(json.dumps(modules, indent=2) + '\n')
print(json.dumps(dict(modules=len(modules), relocations=sum(len(m['relocs']) for m in modules), original_main_plt=hex(plt[0]), original_main_slot=hex(slot))))
