#include "symbol_view.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t image[0x1000];
static MngSymbolLayout layout = {
    .data_off = 0x800, .key_off = 0x900,
    .str_off = 0x100, .str_size = 16,
    .sym_off = 0x200, .symbol_count = 6,
};

static void put_u16(size_t at, uint16_t value) { memcpy(image + at, &value, 2); }
static void put_u32(size_t at, uint32_t value) { memcpy(image + at, &value, 4); }
static void put_u64(size_t at, uint64_t value) { memcpy(image + at, &value, 8); }

static void row(unsigned index, uint32_t name, uint8_t info, uint16_t section,
                uint64_t value, uint64_t size) {
    size_t at = layout.sym_off + index * 24;
    put_u32(at, name);
    image[at + 4] = info;
    put_u16(at + 6, section);
    put_u64(at + 8, value);
    put_u64(at + 16, size);
}

static void setup(void) {
    memset(image, 0, sizeof image);
    memcpy(image + layout.str_off, "\0dup\0only\0zero\0", layout.str_size);
    row(0, 10, 0x12, 1, 0x100, 1);
    row(1, 1, 0x12, 0, 0, 0);
    row(2, 1, 0x12, 1, 0x200, 3);
    row(3, 1, 0x12, 1, 0x210, 4);
    row(4, 5, 0x22, 1, 0x900, 5);
    row(5, 5, 0x12, 1, 0x250, 6);
}

static int valid(void) {
    MngSymbolView view;
    MngSymbol symbol;
    uint32_t index = 0;
    size_t capacity = mng_symbol_index_capacity(layout.symbol_count);
    uint32_t *slots = calloc(capacity, sizeof *slots);
    if (!slots || capacity != 16 || mng_symbol_open(&view, image, sizeof image, &layout) ||
        mng_symbol_at(&view, 4, &symbol) || strcmp(symbol.name, "only") ||
        symbol.value != 0x900 || symbol.size != 5 || !symbol.defined ||
        symbol.binding != 2 || symbol.type != 2 ||
        mng_symbol_index_build(&view, slots, capacity) ||
        mng_symbol_lookup(&view, "dup", &index) != 1 || index != 2 ||
        mng_symbol_lookup(&view, "only", &index) != 0 ||
        mng_symbol_lookup(&view, "zero", &index) != 0 ||
        mng_symbol_lookup(&view, "missing", &index) != 0) {
        free(slots);
        return 1;
    }
    free(slots);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    setup();
    MngSymbolView view;
    if (!strcmp(argv[1], "valid")) return valid();
    if (!strcmp(argv[1], "str_overlap")) {
        layout.str_off = 0x7f8;
        return mng_symbol_open(&view, image, sizeof image, &layout) == MNG_SYMBOL_BOUNDS ? 0 : 1;
    }
    if (!strcmp(argv[1], "sym_overlap")) {
        layout.sym_off = 0x7f0;
        return mng_symbol_open(&view, image, sizeof image, &layout) == MNG_SYMBOL_BOUNDS ? 0 : 1;
    }
    if (!strcmp(argv[1], "bad_offset")) {
        put_u32(layout.sym_off + 24, (uint32_t)layout.str_size);
        return mng_symbol_open(&view, image, sizeof image, &layout) == MNG_SYMBOL_BOUNDS ? 0 : 1;
    }
    if (!strcmp(argv[1], "unterminated")) {
        layout.str_size = 4;
        layout.symbol_count = 2;
        put_u32(layout.sym_off, 0);
        return mng_symbol_open(&view, image, sizeof image, &layout) == MNG_SYMBOL_FORMAT ? 0 : 1;
    }
    if (!strcmp(argv[1], "short_index")) {
        uint32_t slots[8] = {0};
        return mng_symbol_open(&view, image, sizeof image, &layout) == 0 &&
               mng_symbol_index_build(&view, slots, 8) == MNG_SYMBOL_BOUNDS ? 0 : 1;
    }
    fprintf(stderr, "unknown case: %s\n", argv[1]);
    return 2;
}
