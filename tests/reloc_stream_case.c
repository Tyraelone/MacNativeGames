#include "reloc_stream.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { MngReloc rows[8]; unsigned count; int stop; } Seen;

static void put64(uint8_t *image, size_t offset, uint64_t value) {
    memcpy(image + offset, &value, sizeof value);
}

static int record(void *context, const MngReloc *row) {
    Seen *seen = context;
    if (seen->count < 8) seen->rows[seen->count] = *row;
    seen->count++;
    return seen->stop;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    uint8_t image[0x400] = {0};
    MngRelocLayout layout = {
        .data_off = 0x200, .key_off = 0x380, .symbol_count = 2,
        .relr_off = 0x40, .relr_size = 16,
        .rela_off = 0x60, .rela_size = 24,
        .plt_off = 0x90, .plt_size = 24,
    };
    put64(image, 0x40, 0x200);
    put64(image, 0x48, 1 | (1 << 1) | (1 << 3));
    put64(image, 0x200, 0x10);
    put64(image, 0x208, 0x20);
    put64(image, 0x218, 0x30);
    put64(image, 0x60, 0x220);
    put64(image, 0x68, 1027);
    put64(image, 0x70, 0x40);
    put64(image, 0x90, 0x228);
    put64(image, 0x98, ((uint64_t)1 << 32) | 1026);

    Seen seen = {0};
    uint64_t count = 0;
    int expected = MNG_RELOC_OK;
    if (!strcmp(argv[1], "source_overlap")) {
        layout.rela_off = 0x220;
        expected = MNG_RELOC_BOUNDS;
    } else if (!strcmp(argv[1], "bad_kind")) {
        put64(image, 0x68, 9999);
        expected = MNG_RELOC_FORMAT;
    } else if (!strcmp(argv[1], "bad_symbol")) {
        put64(image, 0x98, ((uint64_t)2 << 32) | 1026);
        expected = MNG_RELOC_BOUNDS;
    } else if (!strcmp(argv[1], "bad_target")) {
        put64(image, 0x60, layout.key_off);
        expected = MNG_RELOC_BOUNDS;
    } else if (!strcmp(argv[1], "bitmap_first")) {
        put64(image, 0x40, 3);
        expected = MNG_RELOC_FORMAT;
    } else if (!strcmp(argv[1], "visitor_stop")) {
        seen.stop = 7;
        expected = MNG_RELOC_VISITOR;
    } else if (strcmp(argv[1], "valid")) {
        return 2;
    }
    int result = mng_reloc_walk(image, sizeof image, &layout, record, &seen, &count);
    if (result != expected) {
        fprintf(stderr, "%s: result %d, expected %d\n", argv[1], result, expected);
        return 1;
    }
    if (!strcmp(argv[1], "valid")) {
        if (count != 5 || seen.count != 5 ||
            seen.rows[0].where != 0x200 || seen.rows[0].addend != 0x10 ||
            seen.rows[1].where != 0x208 || seen.rows[1].addend != 0x20 ||
            seen.rows[2].where != 0x218 || seen.rows[2].addend != 0x30 ||
            seen.rows[3].where != 0x220 || seen.rows[3].kind != 1027 ||
            seen.rows[4].where != 0x228 || seen.rows[4].kind != 1026 ||
            seen.rows[4].symbol != 1) return 1;
    }
    if (!strcmp(argv[1], "source_overlap") && count != 0) return 1;
    if (!strcmp(argv[1], "visitor_stop") && count != 1) return 1;
    return 0;
}
