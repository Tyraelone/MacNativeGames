#include "module_gate.h"

#include <stdint.h>
#include <string.h>

static int valid_gates(const MngModuleDescriptor *desc, size_t image_size) {
    if (image_size < 4 || desc->patch_off > image_size ||
        (desc->gate_count && !desc->gates)) return 0;
    for (uint32_t index = 0; index < desc->gate_count; ++index) {
        const MngGateDescriptor *gate = &desc->gates[index];
        if (gate->ret % 4 || gate->ret < desc->patch_off ||
            gate->ret > image_size - 4 || gate->original % 4 ||
            gate->original >= desc->text_end ||
            !((gate->kind == MNG_GATE_SVC && gate->arg <= 0xffff) ||
              ((gate->kind == MNG_GATE_CNTPCT || gate->kind == MNG_GATE_CNTVCT) &&
               gate->arg <= 31)) ||
            (index && desc->gates[index - 1].ret >= gate->ret)) return 0;
    }
    return 1;
}

int mng_gate_table_build(MngGateTable *table, const MngMappedImage *images,
                         size_t module_count) {
    if (!table) return MNG_GATE_TABLE_INVALID;
    memset(table, 0, sizeof *table);
    if (!images || !module_count || module_count > MNG_GATE_MAX_MODULES)
        return MNG_GATE_TABLE_INVALID;
    MngGateTable ready = {0};
    for (size_t index = 0; index < module_count; ++index) {
        const MngMappedImage *image = &images[index];
        const MngModuleDescriptor *desc = image->descriptor;
        uint64_t base = (uintptr_t)image->bytes;
        if (!image->sealed || !image->bytes || !desc ||
            !image->image_size || image->image_size != desc->file_size ||
            image->mapped_size < image->image_size ||
            image->mapped_size > UINT64_MAX - base ||
            !valid_gates(desc, image->image_size))
            return MNG_GATE_TABLE_INVALID;
        MngGateRegion row = {.base = base, .end = base + image->image_size,
                             .mapped_end = base + image->mapped_size,
                             .gates = desc->gates, .gate_count = desc->gate_count,
                             .module_index = index};
        size_t at = ready.count++;
        while (at && ready.regions[at - 1].base > row.base) {
            ready.regions[at] = ready.regions[at - 1];
            --at;
        }
        ready.regions[at] = row;
    }
    for (size_t index = 1; index < ready.count; ++index)
        if (ready.regions[index - 1].mapped_end > ready.regions[index].base)
            return MNG_GATE_TABLE_INVALID;
    *table = ready;
    return 0;
}

int mng_gate_find(const MngGateTable *table, uint64_t return_address,
                  MngGateHit *hit) {
    if (hit) memset(hit, 0, sizeof *hit);
    if (!table || !hit || !table->count || table->count > MNG_GATE_MAX_MODULES)
        return MNG_GATE_INVALID;
    size_t lo = 0, hi = table->count;
    while (lo < hi) {
        size_t middle = lo + (hi - lo) / 2;
        if (return_address < table->regions[middle].base) hi = middle;
        else lo = middle + 1;
    }
    if (!lo) return MNG_GATE_MISSING;
    const MngGateRegion *region = &table->regions[lo - 1];
    if (return_address >= region->end) return MNG_GATE_MISSING;
    uint64_t offset = return_address - region->base;
    lo = 0;
    hi = region->gate_count;
    while (lo < hi) {
        size_t middle = lo + (hi - lo) / 2;
        if (region->gates[middle].ret < offset) lo = middle + 1;
        else hi = middle;
    }
    if (lo == region->gate_count || region->gates[lo].ret != offset)
        return MNG_GATE_MISSING;
    *hit = (MngGateHit){.gate = &region->gates[lo],
                        .module_base = region->base,
                        .module_index = region->module_index};
    return MNG_GATE_FOUND;
}
