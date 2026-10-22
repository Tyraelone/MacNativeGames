#!/usr/bin/env python3
"""Compare Castlevania 1.1.0's pinned indirect branches and SP sites with Unicorn.

Game NSO and rewritten output must remain outside the source repository.
Requires the project's development dependencies, including unicorn==2.1.4.
"""
import argparse
import random
import sys
from pathlib import Path

BUILD_ID = '0f1169aa7d0fa4529c861f96adec306e'
TARGETS = {
    0x375a7ec: (0x101330, 0x101770, 0x101390, 0x101400,
                0x101470, 0x101560, 0x101690, 0x1014e0),
    0x3daf81c: (0x179af0, 0x179f30, 0x179b50, 0x179bc0,
                0x179c30, 0x179d20, 0x179e50, 0x179ca0),
}
SP_SITES = {0x811950: 10, 0x17d68c0: 10, 0x198a300: 8,
            0x34b9f4c: 8, 0x34bb7bc: 8, 0x34c0cb8: 8,
            0x34c2810: 8, 0x34cdb90: 8, 0x34cfa0c: 8}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nso', type=Path, required=True, help='original 1.1.0 main NSO')
    parser.add_argument('--rewrite', type=Path, required=True, help='directory with main.patched.bin and metadata')
    args = parser.parse_args()
    with args.nso.open('rb') as source:
        header = source.read(0x50)
    if header[0x40:0x50].hex() != BUILD_ID:
        parser.error('main NSO build ID does not match the pinned version')
    rows = (args.rewrite / 'main.sites.tsv').read_text().splitlines()
    registered = {int(row.split()[0], 16): row.split()[1] for row in rows}
    if any(registered.get(site) != 'I' for site in TARGETS):
        parser.error('rewritten output lacks the pinned indirect branch sites')
    if any(registered.get(site) != 'x18' for site in SP_SITES):
        parser.error('rewritten output lacks the pinned dynamic SP sites')

    # Reuse the project's register/memory comparison, but only run the new
    # version-specific sites. Its CLI parser runs at import time.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'totk/third_party/d2r'))
    sys.argv = ['equiv.py', str(args.rewrite), 'main', str(args.nso),
                '--mutate', '0', '--jobs', '1']
    import equiv

    original, original_state = equiv.mk(equiv.orig, bytes(equiv.ARENA_SZ))
    rewritten, rewritten_state = equiv.mk(equiv.pat, bytes(equiv.ARENA_SZ))
    rng = random.Random(91273)
    count = 0
    for site, targets in TARGETS.items():
        for target in targets:
            for _ in range(3):
                initial = equiv.init_state(rng, 2)
                initial['g'][18] = equiv.IB + target
                same, both_faulted, fields = equiv.trial(
                    original, original_state, rewritten, rewritten_state, site, initial)
                if not same or both_faulted:
                    raise AssertionError(f'branch {site:#x} -> {target:#x}: {fields}, both_faulted={both_faulted}')
                count += 1
    for site, old_sp_reg in SP_SITES.items():
        for delta in (0, 0x10, 0x80, 0x200):
            initial = equiv.init_state(rng, 2)
            initial['g'][old_sp_reg] = equiv.SP0
            initial['g'][18] = equiv.SP0 - delta
            same, both_faulted, fields = equiv.trial(
                original, original_state, rewritten, rewritten_state, site, initial)
            if not same or both_faulted:
                raise AssertionError(f'dynamic SP {site:#x}, delta {delta:#x}: {fields}, both_faulted={both_faulted}')
            count += 1
    print(f'PASS: {count} paired instruction-level trials')


if __name__ == '__main__':
    main()
