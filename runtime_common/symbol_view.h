#pragma once

#include <stddef.h>
#include <stdint.h>

/* Table layout comes from the hash-verified offline runtime preflight. */
typedef struct {
    uint64_t data_off, key_off;
    uint64_t str_off, str_size;
    uint64_t sym_off;
    uint32_t symbol_count;
} MngSymbolLayout;

typedef struct {
    const char *name; /* Points into the image; the image must outlive this row. */
    uint64_t value, size;
    uint8_t defined, binding, type;
} MngSymbol;

typedef struct {
    const uint8_t *image;
    MngSymbolLayout layout;
    uint32_t *slots; /* Caller owned; each slot holds a nonzero symbol index. */
    uint32_t mask;
} MngSymbolView;

enum {
    MNG_SYMBOL_OK = 0,
    MNG_SYMBOL_FORMAT = 1,
    MNG_SYMBOL_BOUNDS = 2,
};

/* Returns zero for an invalid or unsupported symbol count. */
size_t mng_symbol_index_capacity(uint32_t symbol_count);

/* Validates every symbol name before returning a view of immutable source tables. */
int mng_symbol_open(MngSymbolView *view, const uint8_t *image, size_t image_size,
                    const MngSymbolLayout *layout);
int mng_symbol_at(const MngSymbolView *view, uint32_t index, MngSymbol *symbol);

/* Clears and fills caller-owned slots; capacity must be a suitable power of two. */
int mng_symbol_index_build(MngSymbolView *view, uint32_t *slots, size_t capacity);

/* 1 = found, 0 = absent or first definition outside key_off, -1 = invalid call. */
int mng_symbol_lookup(const MngSymbolView *view, const char *name, uint32_t *index);
