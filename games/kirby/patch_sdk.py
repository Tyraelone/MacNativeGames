#!/usr/bin/env python3
"""Pin the base Kirby SDK image and replace five unsupported HID reads.

This is a boot probe only: it does not supply controller or touch state.
"""

import argparse
import hashlib
from pathlib import Path


ORIGINAL_SHA256 = "41ce5fba16b819156b584b0d96885c153b942b70b1e18a256301e230ae18fe2c"
PROLOGUE = bytes.fromhex("ff8300d1fd7b01a9")
RETURN = bytes.fromhex("c0035fd6")
ZERO_AND_RETURN = bytes.fromhex("e0031f2ac0035fd6")
PATCHES = {
    0x228E48: RETURN,  # GetDebugPadState
    0x228E8C: ZERO_AND_RETURN,  # GetDebugPadStates
    0x22C200: ZERO_AND_RETURN,  # GetNpadJoyAssignment: Dual
    0x22DB00: RETURN,  # GetTouchScreenState<16>
    0x22DB44: ZERO_AND_RETURN,  # GetTouchScreenStates<1>
}


def patch(image: bytes) -> bytes:
    digest = hashlib.sha256(image).hexdigest()
    if digest != ORIGINAL_SHA256:
        raise ValueError(f"unsupported Kirby sdk rewrite: {digest}")
    result = bytearray(image)
    for offset, replacement in PATCHES.items():
        if result[offset:offset + len(PROLOGUE)] != PROLOGUE:
            raise ValueError(f"SDK instruction mismatch at {offset:#x}")
        result[offset:offset + len(replacement)] = replacement
    return bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    args.image.write_bytes(patch(args.image.read_bytes()))
    print(hashlib.sha256(args.image.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
