/* Offline guest-only linker probe; all image and output paths are external. */
#include "guest_link.h"
#include "reloc_apply.h"

#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    const char *name;
    uint8_t *original, *work;
    size_t image_size;
    MngSymbolView view;
    uint32_t *slots;
    MngRelocLayout reloc;
    uint64_t base, count, first_ns, warm_min_ns;
    MngGuestResolver resolver;
} ModuleState;

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

static uint8_t *read_file(const char *path, size_t *length) {
    FILE *file = fopen(path, "rb");
    if (!file) return NULL;
    if (fseek(file, 0, SEEK_END)) {
        fclose(file);
        return NULL;
    }
    long size = ftell(file);
    if (size <= 0 || size > 512L * 1024 * 1024 || fseek(file, 0, SEEK_SET)) {
        fclose(file);
        return NULL;
    }
    uint8_t *bytes = malloc((size_t)size);
    size_t received = bytes ? fread(bytes, 1, (size_t)size, file) : 0;
    int closed = fclose(file);
    if (!bytes || received != (size_t)size || closed) {
        free(bytes);
        return NULL;
    }
    *length = (size_t)size;
    return bytes;
}

static int valid_name(const char *name) {
    size_t length = strlen(name);
    if (!length || length > 31) return 0;
    for (const unsigned char *byte = (const unsigned char *)name; *byte; ++byte)
        if (!isalnum(*byte) && *byte != '_') return 0;
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 19) return 2;
    uint64_t rounds = number(argv[1]), count = number(argv[3]);
    if (rounds < 2 || rounds > 20 || !count || count > 16 || argc != 4 + 15 * (int)count)
        return 2;
    ModuleState *states = calloc((size_t)count, sizeof *states);
    MngGuestModule *guests = calloc((size_t)count, sizeof *guests);
    if (!states || !guests) return 2;
    for (size_t index = 0; index < count; ++index) {
        char **arg = argv + 4 + index * 15;
        ModuleState *state = &states[index];
        if (!valid_name(arg[0])) return 2;
        state->name = arg[0];
        state->original = read_file(arg[1], &state->image_size);
        state->work = malloc(state->image_size);
        if (!state->original || !state->work) return 2;
        memcpy(state->work, state->original, state->image_size);
        state->base = number(arg[2]);
        uint64_t symbol_count = number(arg[8]);
        if (!symbol_count || symbol_count > UINT32_MAX) return 2;
        MngSymbolLayout symbol = {
            .data_off = number(arg[3]), .key_off = number(arg[4]),
            .str_off = number(arg[5]), .str_size = number(arg[6]),
            .sym_off = number(arg[7]), .symbol_count = (uint32_t)symbol_count,
        };
        if (mng_symbol_open(&state->view, state->work, state->image_size, &symbol)) return 1;
        size_t capacity = mng_symbol_index_capacity(symbol.symbol_count);
        state->slots = calloc(capacity, sizeof *state->slots);
        if (!state->slots || mng_symbol_index_build(&state->view, state->slots, capacity)) return 1;
        state->reloc = (MngRelocLayout){
            .data_off = symbol.data_off, .key_off = symbol.key_off,
            .symbol_count = symbol.symbol_count,
            .relr_off = number(arg[9]), .relr_size = number(arg[10]),
            .rela_off = number(arg[11]), .rela_size = number(arg[12]),
            .plt_off = number(arg[13]), .plt_size = number(arg[14]),
        };
        guests[index] = (MngGuestModule){&state->view, state->base};
        state->warm_min_ns = UINT64_MAX;
    }
    for (size_t index = 0; index < count; ++index)
        states[index].resolver = (MngGuestResolver){.modules = guests,
            .module_count = (size_t)count, .current = index};
    for (uint64_t round = 0; round < rounds; ++round) {
        for (size_t index = 0; index < count; ++index)
            memcpy(states[index].work, states[index].original, states[index].image_size);
        for (size_t index = 0; index < count; ++index) {
            ModuleState *state = &states[index];
            state->resolver.local = state->resolver.global = 0;
            state->resolver.weak_zero = state->resolver.host_resolved = 0;
            uint64_t start = now_ns();
            int status = mng_reloc_apply(state->work, state->image_size, &state->reloc,
                                         state->base, mng_guest_resolve,
                                         &state->resolver, &state->count);
            uint64_t elapsed = now_ns() - start;
            if (status) {
                fprintf(stderr, "link failed for %s: %d after %" PRIu64 " writes\n",
                        state->name, status, state->count);
                return 1;
            }
            if (round == 0) state->first_ns = elapsed;
            else if (elapsed < state->warm_min_ns) state->warm_min_ns = elapsed;
        }
    }
    printf("{\"rounds\":%" PRIu64 ",\"modules\":{", rounds);
    for (size_t index = 0; index < count; ++index) {
        ModuleState *state = &states[index];
        char output[4096];
        if (snprintf(output, sizeof output, "%s/%s.linked.bin", argv[2], state->name) >=
            (int)sizeof output) return 2;
        FILE *file = fopen(output, "wb");
        if (!file) return 2;
        size_t written = fwrite(state->work, 1, state->image_size, file);
        int closed = fclose(file);
        if (written != state->image_size || closed) return 2;
        printf("%s\"%s\":{\"relocations\":%" PRIu64
               ",\"local\":%" PRIu64 ",\"global\":%" PRIu64
               ",\"weak_zero\":%" PRIu64 ",\"host\":%" PRIu64
               ",\"first_ns\":%" PRIu64 ",\"warm_min_ns\":%" PRIu64 "}",
               index ? "," : "", state->name, state->count,
               state->resolver.local, state->resolver.global,
               state->resolver.weak_zero, state->resolver.host_resolved,
               state->first_ns, state->warm_min_ns);
        free(state->slots);
        free(state->work);
        free(state->original);
    }
    printf("}}\n");
    free(guests);
    free(states);
    return 0;
}
