#include "reloc_apply.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static void put64(uint8_t *image, size_t offset, uint64_t value) {
    memcpy(image + offset, &value, sizeof value);
}

static uint64_t get64(const uint8_t *image, size_t offset) {
    uint64_t value;
    memcpy(&value, image + offset, sizeof value);
    return value;
}

typedef struct { unsigned calls; int fail_symbol; } Resolver;

static int resolve(void *context, uint32_t symbol, uint32_t kind, uint64_t *address) {
    Resolver *state = context;
    state->calls++;
    if ((int)symbol == state->fail_symbol ||
        (kind != 257 && kind != 1025 && kind != 1026)) return 1;
    *address = UINT64_C(0x5000) + (uint64_t)symbol * 0x1000;
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    uint8_t image[0x400] = {0};
    MngRelocLayout layout = {
        .data_off = 0x200, .key_off = 0x380, .symbol_count = 3,
        .relr_off = 0x40, .relr_size = 16,
        .rela_off = 0x60, .rela_size = 72,
        .plt_off = 0xb0, .plt_size = 24,
    };
    put64(image, 0x40, 0x200);
    put64(image, 0x48, 1 | (1 << 1) | (1 << 3));
    put64(image, 0x200, 0x10);
    put64(image, 0x208, 0x20);
    put64(image, 0x218, 0x30);
    put64(image, 0x60, 0x220);
    put64(image, 0x68, ((uint64_t)1 << 32) | 257);
    put64(image, 0x70, UINT64_MAX - 7);  /* -8 */
    put64(image, 0x78, 0x228);
    put64(image, 0x80, ((uint64_t)2 << 32) | 1025);
    put64(image, 0x88, 16);
    put64(image, 0x90, 0x230);
    put64(image, 0x98, 1027);
    put64(image, 0xa0, 0x40);
    put64(image, 0xb0, 0x238);
    put64(image, 0xb8, ((uint64_t)1 << 32) | 1026);
    put64(image, 0xc0, 0x123);  /* PLT addend is ignored by the current loader */

    Resolver state = {.fail_symbol = -1};
    uint64_t count = UINT64_MAX;
    int expected = MNG_RELOC_OK;
    if (!strcmp(argv[1], "source_overlap")) {
        layout.rela_off = 0x220;
        expected = MNG_RELOC_BOUNDS;
    } else if (!strcmp(argv[1], "resolve_failure")) {
        state.fail_symbol = 2;
        expected = MNG_RELOC_RESOLVE;
    } else if (strcmp(argv[1], "valid")) {
        return 2;
    }
    int result = mng_reloc_apply(image, sizeof image, &layout, UINT64_C(0x100000000),
                                 resolve, &state, &count);
    if (result != expected) {
        fprintf(stderr, "%s: status %d, expected %d\n", argv[1], result, expected);
        return 1;
    }
    if (!strcmp(argv[1], "valid")) {
        if (count != 7 || state.calls != 3 ||
            get64(image, 0x200) != UINT64_C(0x100000010) ||
            get64(image, 0x208) != UINT64_C(0x100000020) ||
            get64(image, 0x218) != UINT64_C(0x100000030) ||
            get64(image, 0x220) != UINT64_C(0x5ff8) ||
            get64(image, 0x228) != UINT64_C(0x7010) ||
            get64(image, 0x230) != UINT64_C(0x100000040) ||
            get64(image, 0x238) != UINT64_C(0x6000)) return 1;
    }
    if (!strcmp(argv[1], "source_overlap") &&
        (count != 0 || state.calls || get64(image, 0x200) != 0x10 ||
         get64(image, 0x220) != 0)) return 1;
    if (!strcmp(argv[1], "resolve_failure") &&
        (count != 4 || state.calls != 2 || get64(image, 0x220) != 0x5ff8 ||
         get64(image, 0x228) != 0 || get64(image, 0x230) != 0 ||
         get64(image, 0x238) != 0)) return 1;
    return 0;
}
