#pragma once

#include "reloc_stream.h"

typedef int (*MngRelocResolve)(void *context, uint32_t symbol, uint32_t kind,
                               uint64_t *address);

enum { MNG_RELOC_RESOLVE = 4 };

/* Preflighted tables must also precede data_off; otherwise no writes occur.
 * Count reports completed writes. Any failure after writes makes the image
 * unsuitable for in-place retry: discard it and load a fresh verified copy. */
int mng_reloc_apply(uint8_t *image, size_t image_size,
                    const MngRelocLayout *layout, uint64_t base,
                    MngRelocResolve resolve, void *context, uint64_t *count);
