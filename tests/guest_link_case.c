#include "guest_link.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t images[2][0x1000];
static MngSymbolView views[2];
static uint32_t slots[2][32];
static MngGuestModule modules[2];

static void row(uint8_t *image, unsigned index, uint32_t name, uint8_t info,
                uint16_t section, uint64_t value) {
    size_t at = 0x200 + index * 24;
    memcpy(image + at, &name, 4);
    image[at + 4] = info;
    memcpy(image + at + 6, &section, 2);
    memcpy(image + at + 8, &value, 8);
}

static int setup(void) {
    static const char names[] = "\0local\0shared\0weak\0optional\0missing\0bad\0dupe\0";
    MngSymbolLayout layout = {.data_off = 0x800, .key_off = 0x900,
                              .str_off = 0x100, .str_size = sizeof names,
                              .sym_off = 0x200, .symbol_count = 7};
    for (unsigned i = 0; i < 2; ++i)
        memcpy(images[i] + 0x100, names, sizeof names);
    row(images[0], 1, 1, 0x12, 1, 0x200);
    row(images[0], 2, 7, 0x12, 1, 0x210);
    row(images[0], 3, 14, 0x12, 1, 0x220);
    row(images[0], 4, 36, 0x12, 1, 0x900);
    row(images[0], 5, 40, 0x12, 1, 0x900);
    row(images[0], 6, 40, 0x12, 1, 0x230);
    row(images[1], 1, 7, 0x12, 0, 0);
    row(images[1], 2, 14, 0x22, 1, 0x240);
    row(images[1], 3, 19, 0x22, 0, 0);
    row(images[1], 4, 28, 0x12, 0, 0);
    row(images[1], 5, 40, 0x12, 0, 0);
    layout.symbol_count = 7;
    if (mng_symbol_open(&views[0], images[0], sizeof images[0], &layout) ||
        mng_symbol_index_build(&views[0], slots[0], 32)) return 1;
    layout.symbol_count = 6;
    if (mng_symbol_open(&views[1], images[1], sizeof images[1], &layout) ||
        mng_symbol_index_build(&views[1], slots[1], 32)) return 1;
    modules[0] = (MngGuestModule){&views[0], UINT64_C(0x100000000)};
    modules[1] = (MngGuestModule){&views[1], UINT64_C(0x200000000)};
    return 0;
}

static int host(void *context, const char *name, uint32_t kind, uint64_t *address) {
    (void)context;
    if (!strcmp(name, "local")) {
        if (kind != 257) return -1;
        *address = UINT64_C(0x300000000);
        return 1;
    }
    if (!strcmp(name, "missing")) return -1;
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2 || setup()) return 2;
    MngGuestResolver resolver = {.modules = modules, .module_count = 2};
    uint64_t address = 0;
    if (!strcmp(argv[1], "guest")) {
        resolver.current = 0;
        if (mng_guest_resolve(&resolver, 1, 257, &address) ||
            address != UINT64_C(0x100000200)) return 1;
        resolver.current = 1;
        if (mng_guest_resolve(&resolver, 1, 257, &address) ||
            address != UINT64_C(0x100000210)) return 1;
        if (mng_guest_resolve(&resolver, 2, 1026, &address) ||
            address != UINT64_C(0x100000220)) return 1;
        if (mng_guest_resolve(&resolver, 3, 1025, &address) || address != 0) return 1;
        return resolver.local == 1 && resolver.global == 2 && resolver.weak_zero == 1 ? 0 : 1;
    }
    if (!strcmp(argv[1], "host")) {
        resolver.host = host;
        if (mng_guest_resolve(&resolver, 1, 257, &address) ||
            address != UINT64_C(0x300000000) || resolver.host_resolved != 1) return 1;
        resolver.current = 1;
        return mng_guest_resolve(&resolver, 4, 257, &address) == MNG_GUEST_HOST_ERROR ? 0 : 1;
    }
    if (!strcmp(argv[1], "missing")) {
        resolver.current = 1;
        return mng_guest_resolve(&resolver, 4, 257, &address) == MNG_GUEST_UNRESOLVED &&
               mng_guest_resolve(&resolver, 5, 257, &address) == MNG_GUEST_UNRESOLVED ? 0 : 1;
    }
    if (!strcmp(argv[1], "bounds")) {
        return mng_guest_resolve(&resolver, 4, 257, &address) == MNG_GUEST_UNRESOLVED &&
               mng_guest_resolve(&resolver, 7, 257, &address) == MNG_GUEST_FORMAT &&
               (modules[0].base = UINT64_MAX - 0x100,
                mng_guest_resolve(&resolver, 1, 257, &address) == MNG_GUEST_FORMAT) ? 0 : 1;
    }
    fprintf(stderr, "unknown case\n");
    return 2;
}
