#pragma once
#include "runtime.h"

/* TOTK version-specific game-code patches, applied to the loaded main module after relocation and before its text is sealed.
   Every site is checked against the original instruction word first; a mismatch stops the boot. */
void runtime_game_patches(Module *main_module);
void runtime_game_patch_trap_only(Module *main_module);
#ifdef CASTLEVANIA_NATIVE_PROBE
static const uint32_t castlevania_bounds_sites[] = {
    0x1f73a8c, 0x1f73ac4, 0x1f73ae8, 0x1f73b1c, 0x1f73b4c, 0x1f73b80,
    0x1f73c04, 0x1f73cbc, 0x1f73d10, 0x1f73d60, 0x1f73db0
};
static const struct { uint32_t off; uint8_t reg; } castlevania_null_sites[] = {
    {0x1f73a80,8},{0x1f73a9c,0},{0x1f73aa8,0},{0x1f73ab8,8},
    {0x1f73adc,8},{0x1f73af4,0},{0x1f73b00,0},{0x1f73b10,8},
    {0x1f73b40,8},{0x1f73b58,0},{0x1f73b64,0},{0x1f73b74,8},
    {0x1f73ba4,0},{0x1f73bb8,0},{0x1f73bd0,0},{0x1f73bf8,8},
    {0x1f73c10,0},{0x1f73c48,21},{0x1f73cb0,8},{0x1f73cc8,0},
    {0x1f73d04,8},{0x1f73d1c,0},{0x1f73d30,0},{0x1f73d54,8},
    {0x1f73d6c,0},{0x1f73d80,0},{0x1f73da4,8},{0x1f73dbc,0},
    {0x1f73dd0,0}
};
#endif
