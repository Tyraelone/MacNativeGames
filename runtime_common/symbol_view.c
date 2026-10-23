#include "symbol_view.h"

#include <limits.h>
#include <string.h>

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Switch and Apple ARM64 symbol tables require a little-endian host"
#endif

enum { SYMBOL_ENTRY_SIZE = 24, MAX_SYMBOLS = 1000000, MAX_STRINGS = 16 * 1024 * 1024 };

static uint16_t read_u16(const uint8_t *address) {
    uint16_t value;
    memcpy(&value, address, sizeof value);
    return value;
}

static uint32_t read_u32(const uint8_t *address) {
    uint32_t value;
    memcpy(&value, address, sizeof value);
    return value;
}

static uint64_t read_u64(const uint8_t *address) {
    uint64_t value;
    memcpy(&value, address, sizeof value);
    return value;
}

static uint32_t hash_name(const char *name) {
    uint32_t hash = UINT32_C(2166136261);
    for (const unsigned char *byte = (const unsigned char *)name; *byte; ++byte)
        hash = (hash ^ *byte) * UINT32_C(16777619);
    return hash;
}

size_t mng_symbol_index_capacity(uint32_t symbol_count) {
    if (!symbol_count || symbol_count > MAX_SYMBOLS) return 0;
    size_t capacity = 16;
    while (capacity < (size_t)symbol_count * 2) capacity <<= 1;
    return capacity;
}

int mng_symbol_open(MngSymbolView *view, const uint8_t *image, size_t image_size,
                    const MngSymbolLayout *layout) {
    if (!view) return MNG_SYMBOL_FORMAT;
    memset(view, 0, sizeof *view);
    if (!image || !layout || !mng_symbol_index_capacity(layout->symbol_count) ||
        !layout->str_size || layout->str_size > MAX_STRINGS)
        return MNG_SYMBOL_FORMAT;
    if (layout->data_off >= layout->key_off || layout->key_off > image_size ||
        layout->str_off > layout->data_off ||
        layout->str_size > layout->data_off - layout->str_off ||
        layout->sym_off > layout->data_off ||
        (uint64_t)layout->symbol_count * SYMBOL_ENTRY_SIZE >
            layout->data_off - layout->sym_off)
        return MNG_SYMBOL_BOUNDS;
    for (uint32_t index = 0; index < layout->symbol_count; ++index) {
        const uint8_t *entry = image + layout->sym_off + (uint64_t)index * SYMBOL_ENTRY_SIZE;
        uint32_t offset = read_u32(entry);
        if (offset >= layout->str_size) return MNG_SYMBOL_BOUNDS;
        const uint8_t *name = image + layout->str_off + offset;
        if (!memchr(name, 0, (size_t)(layout->str_size - offset)))
            return MNG_SYMBOL_FORMAT;
    }
    view->image = image;
    view->layout = *layout;
    return MNG_SYMBOL_OK;
}

int mng_symbol_at(const MngSymbolView *view, uint32_t index, MngSymbol *symbol) {
    if (!view || !view->image || !symbol) return MNG_SYMBOL_FORMAT;
    if (index >= view->layout.symbol_count) return MNG_SYMBOL_BOUNDS;
    const uint8_t *entry = view->image + view->layout.sym_off + (uint64_t)index * SYMBOL_ENTRY_SIZE;
    uint32_t offset = read_u32(entry);
    uint8_t info = entry[4];
    *symbol = (MngSymbol){
        .name = (const char *)(view->image + view->layout.str_off + offset),
        .value = read_u64(entry + 8), .size = read_u64(entry + 16),
        .defined = read_u16(entry + 6) != 0,
        .binding = info >> 4, .type = info & 15,
    };
    return MNG_SYMBOL_OK;
}

int mng_symbol_index_build(MngSymbolView *view, uint32_t *slots, size_t capacity) {
    if (!view || !view->image || !slots) return MNG_SYMBOL_FORMAT;
    if (capacity < mng_symbol_index_capacity(view->layout.symbol_count) ||
        capacity > UINT32_MAX || capacity > SIZE_MAX / sizeof *slots ||
        (capacity & (capacity - 1)))
        return MNG_SYMBOL_BOUNDS;
    memset(slots, 0, capacity * sizeof *slots);
    uint32_t mask = (uint32_t)capacity - 1;
    for (uint32_t index = 1; index < view->layout.symbol_count; ++index) {
        MngSymbol symbol;
        mng_symbol_at(view, index, &symbol);
        if (!symbol.defined) continue;
        uint32_t slot = hash_name(symbol.name) & mask;
        while (slots[slot]) {
            MngSymbol existing;
            mng_symbol_at(view, slots[slot], &existing);
            if (!strcmp(symbol.name, existing.name)) break;
            slot = (slot + 1) & mask;
        }
        if (!slots[slot]) slots[slot] = index;
    }
    view->slots = slots;
    view->mask = mask;
    return MNG_SYMBOL_OK;
}

int mng_symbol_lookup(const MngSymbolView *view, const char *name, uint32_t *index) {
    if (!view || !view->image || !view->slots || !name || !index) return -1;
    uint32_t slot = hash_name(name) & view->mask;
    while (view->slots[slot]) {
        MngSymbol symbol;
        uint32_t found = view->slots[slot];
        mng_symbol_at(view, found, &symbol);
        if (!strcmp(name, symbol.name)) {
            if (symbol.value >= view->layout.key_off) return 0;
            *index = found;
            return 1;
        }
        slot = (slot + 1) & view->mask;
    }
    return 0;
}
