#pragma once

#include <stddef.h>
#include <stdint.h>

/* Offsets and sizes come from the verified offline runtime preflight. */
typedef struct {
    uint64_t data_off, key_off;
    uint64_t relr_off, relr_size;
    uint64_t rela_off, rela_size;
    uint64_t plt_off, plt_size;
    uint32_t symbol_count;
} MngRelocLayout;

typedef struct {
    uint64_t where;
    uint32_t kind, symbol;
    int64_t addend;
} MngReloc;

typedef int (*MngRelocVisit)(void *context, const MngReloc *relocation);

enum {
    MNG_RELOC_OK = 0,
    MNG_RELOC_FORMAT = 1,
    MNG_RELOC_BOUNDS = 2,
    MNG_RELOC_VISITOR = 3,
};

/* Source tables must precede data_off, so visit may safely write relocation targets. */
int mng_reloc_walk(const uint8_t *image, size_t image_size,
                   const MngRelocLayout *layout, MngRelocVisit visit,
                   void *context, uint64_t *count);
