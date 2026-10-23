#pragma once

#include "module_image.h"

enum { MNG_GATE_MAX_MODULES = 16 };

typedef struct {
    uint64_t base, end, mapped_end;
    const MngGateDescriptor *gates;
    uint32_t gate_count;
    size_t module_index;
} MngGateRegion;

typedef struct {
    MngGateRegion regions[MNG_GATE_MAX_MODULES];
    size_t count;
} MngGateTable;

typedef struct {
    const MngGateDescriptor *gate;
    uint64_t module_base;
    size_t module_index;
} MngGateHit;

enum {
    MNG_GATE_INVALID = -1,
    MNG_GATE_MISSING = 0,
    MNG_GATE_FOUND = 1,
    MNG_GATE_TABLE_INVALID = 2,
};

/* Build once after every image has linked and sealed. Retain immutable gate
 * rows and mapped images for the lifetime of this table. No heap allocation. */
int mng_gate_table_build(MngGateTable *table, const MngMappedImage *images,
                         size_t module_count);

/* Return address is the PC immediately after a patched gate instruction.
 * Lookup performs binary search over modules and each module's gate rows. */
int mng_gate_find(const MngGateTable *table, uint64_t return_address,
                  MngGateHit *hit);
