#include "symbol_view.h"

#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* Same row layout and hash rule as the existing game loader's flat symbols. */
typedef struct {
    const char *name;
    uint64_t value, size;
    unsigned defined, binding, type;
} FlatSymbol;
_Static_assert(sizeof(FlatSymbol) == 40, "flat loader symbol row size changed");

static uint32_t hash_name(const char *name) {
    uint32_t hash = UINT32_C(2166136261);
    for (const unsigned char *byte = (const unsigned char *)name; *byte; ++byte)
        hash = (hash ^ *byte) * UINT32_C(16777619);
    return hash;
}

static void flat_build(const FlatSymbol *symbols, uint32_t count,
                       uint32_t *slots, uint32_t mask) {
    memset(slots, 0, ((size_t)mask + 1) * sizeof *slots);
    for (uint32_t index = 1; index < count; ++index) {
        if (!symbols[index].defined) continue;
        const char *name = symbols[index].name;
        uint32_t slot = hash_name(name) & mask;
        while (slots[slot] && strcmp(name, symbols[slots[slot]].name))
            slot = (slot + 1) & mask;
        if (!slots[slot]) slots[slot] = index;
    }
}

static uint32_t flat_lookup(const FlatSymbol *symbols, const uint32_t *slots,
                            uint32_t mask, uint64_t key_off, const char *name) {
    uint32_t slot = hash_name(name) & mask;
    while (slots[slot]) {
        uint32_t index = slots[slot];
        if (!strcmp(name, symbols[index].name))
            return symbols[index].value < key_off ? index : 0;
        slot = (slot + 1) & mask;
    }
    return 0;
}

static uint64_t number(const char *text) {
    char *end = NULL;
    errno = 0;
    unsigned long long value = strtoull(text, &end, 0);
    if (errno || !end || *end) {
        fprintf(stderr, "invalid number: %s\n", text);
        exit(2);
    }
    return (uint64_t)value;
}

static uint64_t now_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) exit(2);
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

static void write_hex(FILE *stream, const char *name) {
    for (const unsigned char *byte = (const unsigned char *)name; *byte; ++byte)
        fprintf(stream, "%02x", *byte);
}

int main(int argc, char **argv) {
    if (argc != 11) {
        fprintf(stderr, "usage: probe IMAGE DATA_OFF KEY_OFF STR_OFF STR_SIZE "
                        "SYM_OFF SYMBOL_COUNT ROUNDS ROWS_TSV LOOKUPS_TSV\n");
        return 2;
    }
    FILE *file = fopen(argv[1], "rb");
    if (!file || fseek(file, 0, SEEK_END)) return 2;
    long length = ftell(file);
    if (length < 0 || length > 512L * 1024 * 1024 || fseek(file, 0, SEEK_SET)) return 2;
    uint8_t *image = malloc((size_t)length);
    if (!image || fread(image, 1, (size_t)length, file) != (size_t)length || fclose(file)) return 2;
    uint64_t count = number(argv[7]), rounds = number(argv[8]);
    if (!count || count > UINT32_MAX || !rounds || rounds > 20) return 2;
    MngSymbolLayout layout = {
        .data_off = number(argv[2]), .key_off = number(argv[3]),
        .str_off = number(argv[4]), .str_size = number(argv[5]),
        .sym_off = number(argv[6]), .symbol_count = (uint32_t)count,
    };
    size_t capacity = mng_symbol_index_capacity(layout.symbol_count);
    uint32_t *slots = calloc(capacity, sizeof *slots);
    uint32_t *flat_slots = calloc(capacity, sizeof *flat_slots);
    FlatSymbol *flat = calloc(layout.symbol_count, sizeof *flat);
    if (!slots || !flat_slots || !flat) return 2;
    MngSymbolView view;
    if (mng_symbol_open(&view, image, (size_t)length, &layout)) return 1;
    for (uint32_t index = 0; index < layout.symbol_count; ++index) {
        MngSymbol symbol;
        if (mng_symbol_at(&view, index, &symbol)) return 1;
        flat[index] = (FlatSymbol){symbol.name, symbol.value, symbol.size,
                                   symbol.defined, symbol.binding, symbol.type};
    }
    uint64_t first_setup_ns = 0, warm_setup_ns = UINT64_MAX;
    uint64_t first_lookup_ns = 0, warm_lookup_ns = UINT64_MAX;
    uint64_t first_flat_setup_ns = 0, warm_flat_setup_ns = UINT64_MAX;
    uint64_t first_flat_lookup_ns = 0, warm_flat_lookup_ns = UINT64_MAX;
    uint64_t checksum = 0, flat_checksum = 0;
    for (uint64_t round = 0; round < rounds; ++round) {
        uint64_t setup_ns = 0, lookup_ns = 0, flat_setup_ns = 0, flat_lookup_ns = 0;
        for (unsigned phase = 0; phase < 2; ++phase) {
            uint64_t start = now_ns();
            if ((round + phase) % 2 == 0) {
                int status = mng_symbol_open(&view, image, (size_t)length, &layout);
                if (!status) status = mng_symbol_index_build(&view, slots, capacity);
                setup_ns = now_ns() - start;
                if (status) {
                    fprintf(stderr, "symbol view failed: %d\n", status);
                    return 1;
                }
                start = now_ns();
                checksum = 0;
                for (size_t slot = 0; slot < capacity; ++slot) {
                    if (!slots[slot]) continue;
                    MngSymbol symbol;
                    uint32_t found = 0;
                    mng_symbol_at(&view, slots[slot], &symbol);
                    int result = mng_symbol_lookup(&view, symbol.name, &found);
                    if (result < 0) return 1;
                    checksum = checksum * UINT64_C(1099511628211) ^ found ^ (uint32_t)result;
                }
                lookup_ns = now_ns() - start;
            } else {
                flat_build(flat, layout.symbol_count, flat_slots, (uint32_t)capacity - 1);
                flat_setup_ns = now_ns() - start;
                start = now_ns();
                flat_checksum = 0;
                for (size_t slot = 0; slot < capacity; ++slot) {
                    if (!flat_slots[slot]) continue;
                    uint32_t found = flat_lookup(flat, flat_slots, (uint32_t)capacity - 1,
                                                 layout.key_off, flat[flat_slots[slot]].name);
                    flat_checksum = flat_checksum * UINT64_C(1099511628211) ^ found ^ (found != 0);
                }
                flat_lookup_ns = now_ns() - start;
            }
        }
        if (checksum != flat_checksum) {
            fprintf(stderr, "direct and flat lookup disagree\n");
            return 1;
        }
        if (round == 0) {
            first_setup_ns = setup_ns;
            first_lookup_ns = lookup_ns;
            first_flat_setup_ns = flat_setup_ns;
            first_flat_lookup_ns = flat_lookup_ns;
        } else {
            if (setup_ns < warm_setup_ns) warm_setup_ns = setup_ns;
            if (lookup_ns < warm_lookup_ns) warm_lookup_ns = lookup_ns;
            if (flat_setup_ns < warm_flat_setup_ns) warm_flat_setup_ns = flat_setup_ns;
            if (flat_lookup_ns < warm_flat_lookup_ns) warm_flat_lookup_ns = flat_lookup_ns;
        }
    }
    FILE *rows = fopen(argv[9], "wb"), *lookups = fopen(argv[10], "wb");
    if (!rows || !lookups) return 2;
    for (uint32_t index = 0; index < layout.symbol_count; ++index) {
        MngSymbol symbol;
        if (mng_symbol_at(&view, index, &symbol)) return 1;
        fprintf(rows, "%u\t", index);
        write_hex(rows, symbol.name);
        fprintf(rows, "\t%" PRIu64 "\t%" PRIu64 "\t%u\t%u\t%u\n",
                symbol.value, symbol.size, symbol.defined, symbol.binding, symbol.type);
    }
    uint32_t definitions = 0;
    for (size_t slot = 0; slot < capacity; ++slot) {
        if (!slots[slot]) continue;
        MngSymbol symbol;
        uint32_t found = 0;
        if (mng_symbol_at(&view, slots[slot], &symbol)) return 1;
        if (mng_symbol_lookup(&view, symbol.name, &found) < 0) return 1;
        write_hex(lookups, symbol.name);
        fprintf(lookups, "\t%u\n", found);
        ++definitions;
    }
    if (fclose(rows) || fclose(lookups)) return 2;
    printf("{\"symbols\":%u,\"definitions\":%u,\"index_bytes\":%zu,"
           "\"first_setup_ns\":%" PRIu64 ",\"warm_min_setup_ns\":%" PRIu64
           ",\"first_lookup_ns\":%" PRIu64 ",\"warm_min_lookup_ns\":%" PRIu64
           ",\"first_flat_setup_ns\":%" PRIu64
           ",\"warm_min_flat_setup_ns\":%" PRIu64
           ",\"first_flat_lookup_ns\":%" PRIu64
           ",\"warm_min_flat_lookup_ns\":%" PRIu64
           ",\"lookup_checksum\":%" PRIu64 ",\"flat_lookup_checksum\":%" PRIu64
           ",\"flat_row_bytes\":%zu,\"rounds\":%" PRIu64 "}\n",
           layout.symbol_count, definitions, capacity * sizeof *slots,
           first_setup_ns, rounds > 1 ? warm_setup_ns : 0,
           first_lookup_ns, rounds > 1 ? warm_lookup_ns : 0,
           first_flat_setup_ns, rounds > 1 ? warm_flat_setup_ns : 0,
           first_flat_lookup_ns, rounds > 1 ? warm_flat_lookup_ns : 0,
           checksum, flat_checksum, sizeof *flat * layout.symbol_count, rounds);
    free(flat);
    free(flat_slots);
    free(slots);
    free(image);
    return 0;
}
