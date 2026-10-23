#include "module_gate.h"

#include <stdint.h>
#include <string.h>

static const MngGateDescriptor main_gates[] = {
    {.ret = 0x10004, .original = 0x100, .kind = MNG_GATE_SVC, .arg = 12},
    {.ret = 0x10020, .original = 0x104, .kind = MNG_GATE_CNTPCT, .arg = 3},
};
static const MngGateDescriptor sdk_gates[] = {
    {.ret = 0x10008, .original = 0x200, .kind = MNG_GATE_CNTVCT, .arg = 5},
};

static MngModuleDescriptor descriptor(const char *name,
                                      const MngGateDescriptor *gates, uint32_t count) {
    return (MngModuleDescriptor){.name = name, .file_size = 0x14000,
        .text_end = 0x4000, .ro_off = 0x4000, .data_off = 0x8000,
        .key_off = 0xc000, .key_page_size = 0x4000, .patch_off = 0x10000,
        .gates = gates, .gate_count = count};
}

static int run_lookup(void) {
    MngModuleDescriptor main = descriptor("main", main_gates, 2);
    MngModuleDescriptor sdk = descriptor("sdk", sdk_gates, 1);
    MngMappedImage images[2] = {
        {.descriptor = &sdk, .bytes = (uint8_t *)(uintptr_t)0x500000,
         .image_size = 0x14000, .mapped_size = 0x14000, .sealed = 1},
        {.descriptor = &main, .bytes = (uint8_t *)(uintptr_t)0x100000,
         .image_size = 0x14000, .mapped_size = 0x14000, .sealed = 1},
    };
    MngGateTable table = {0};
    if (mng_gate_table_build(&table, images, 2) || table.count != 2) return 1;
    MngGateHit hit = {0};
    if (mng_gate_find(&table, 0x110020, &hit) != MNG_GATE_FOUND ||
        hit.module_index != 1 || hit.module_base != 0x100000 ||
        hit.gate != &main_gates[1] || hit.gate->kind != MNG_GATE_CNTPCT) return 2;
    if (mng_gate_find(&table, 0x510008, &hit) != MNG_GATE_FOUND ||
        hit.module_index != 0 || hit.gate != &sdk_gates[0]) return 3;
    if (mng_gate_find(&table, 0x11001c, &hit) != MNG_GATE_MISSING ||
        hit.gate || hit.module_base) return 4;
    if (mng_gate_find(&table, 0x514000, &hit) != MNG_GATE_MISSING || hit.gate)
        return 5;
    if (mng_gate_find(&table, 0x100000, &hit) != MNG_GATE_MISSING || hit.gate)
        return 6;
    return 0;
}

static int run_invalid(void) {
    MngModuleDescriptor main = descriptor("main", main_gates, 2);
    MngModuleDescriptor sdk = descriptor("sdk", sdk_gates, 1);
    MngMappedImage images[2] = {
        {.descriptor = &main, .bytes = (uint8_t *)(uintptr_t)0x100000,
         .image_size = 0x14000, .mapped_size = 0x14000, .sealed = 1},
        {.descriptor = &sdk, .bytes = (uint8_t *)(uintptr_t)0x500000,
         .image_size = 0x14000, .mapped_size = 0x14000, .sealed = 1},
    };
    MngGateTable table = {0};
    MngGateHit hit = {0};
    if (mng_gate_table_build(&table, images, 0) != MNG_GATE_TABLE_INVALID ||
        mng_gate_find(&table, 0x110004, &hit) != MNG_GATE_INVALID) return 1;
    images[1].sealed = 0;
    if (mng_gate_table_build(&table, images, 2) != MNG_GATE_TABLE_INVALID ||
        table.count) return 2;
    images[1].sealed = 1;
    images[1].bytes = (uint8_t *)(uintptr_t)0x110000;
    if (mng_gate_table_build(&table, images, 2) != MNG_GATE_TABLE_INVALID ||
        table.count) return 3;
    images[1].bytes = (uint8_t *)(uintptr_t)0x500000;
    static const MngGateDescriptor unsorted[] = {
        {.ret = 0x10020, .original = 0x100, .kind = MNG_GATE_SVC, .arg = 1},
        {.ret = 0x10004, .original = 0x104, .kind = MNG_GATE_SVC, .arg = 2},
    };
    main.gates = unsorted;
    if (mng_gate_table_build(&table, images, 2) != MNG_GATE_TABLE_INVALID ||
        table.count) return 4;
    main.gates = main_gates;
    images[0].bytes = (uint8_t *)(uintptr_t)(UINTPTR_MAX - 0x1000);
    if (mng_gate_table_build(&table, images, 2) != MNG_GATE_TABLE_INVALID ||
        table.count) return 5;
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 90;
    if (!strcmp(argv[1], "lookup")) return run_lookup();
    if (!strcmp(argv[1], "invalid")) return run_invalid();
    return 91;
}
