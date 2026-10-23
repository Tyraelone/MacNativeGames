#include "reloc_apply.h"

#include <string.h>

typedef struct {
    uint8_t *image;
    uint64_t base;
    MngRelocResolve resolve;
    void *resolve_context;
    uint64_t written;
    int resolve_failed;
} ApplyContext;

static int apply_one(void *opaque, const MngReloc *row) {
    ApplyContext *context = opaque;
    uint64_t value;
    if (row->kind == 1027) {
        value = context->base + (uint64_t)row->addend;
    } else {
        if (context->resolve(context->resolve_context, row->symbol, row->kind, &value)) {
            context->resolve_failed = 1;
            return 1;
        }
        if (row->kind != 1026) value += (uint64_t)row->addend;
    }
    memcpy(context->image + row->where, &value, sizeof value);
    context->written++;
    return 0;
}

int mng_reloc_apply(uint8_t *image, size_t image_size,
                    const MngRelocLayout *layout, uint64_t base,
                    MngRelocResolve resolve, void *context, uint64_t *count) {
    if (!count) return MNG_RELOC_FORMAT;
    *count = 0;
    if (!resolve) return MNG_RELOC_FORMAT;
    ApplyContext state = {.image = image, .base = base,
                          .resolve = resolve, .resolve_context = context};
    uint64_t visited = 0;
    int status = mng_reloc_walk(image, image_size, layout, apply_one, &state, &visited);
    *count = state.written;
    return state.resolve_failed ? MNG_RELOC_RESOLVE : status;
}
