#pragma once

#include <stddef.h>
#include <stdint.h>

#include "reloc_stream.h"
#include "symbol_view.h"

enum {
    MNG_GATE_SVC = 1,
    MNG_GATE_CNTPCT = 2,
    MNG_GATE_CNTVCT = 3,
};

typedef struct {
    uint64_t ret, original;
    uint32_t kind, arg;
} MngGateDescriptor;

/* The digest identifies the offline-verified image; callers must verify it before use. */
typedef struct {
    const char *name, *sha256;
    uint64_t file_size, text_end, ro_off, data_off;
    uint64_t key_off, key_page_size, patch_off;
    MngSymbolLayout symbols;
    MngRelocLayout relocations;
    const MngGateDescriptor *gates;
    uint32_t gate_count;
} MngModuleDescriptor;

enum { MNG_DESCRIPTOR_OK = 0, MNG_DESCRIPTOR_INVALID = 1 };

/* Validates source table and gate bounds without allocating a flat table. */
int mng_module_descriptor_check(const MngModuleDescriptor *descriptor,
                                const uint8_t *image, size_t image_size,
                                uint64_t *relocation_count);
