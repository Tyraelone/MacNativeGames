/* Offline descriptor-driven linker; images and output remain outside source. */
#include "module_link.h"
#include "module-table.h"

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    uint8_t *original, *work;
    uint32_t *slots;
    size_t size, capacity;
} ImageState;

static uint64_t now_ns(void) {
    struct timespec time;
    if (clock_gettime(CLOCK_MONOTONIC, &time)) exit(2);
    return (uint64_t)time.tv_sec * UINT64_C(1000000000) + (uint64_t)time.tv_nsec;
}

static int load_image(const char *directory, const MngModuleDescriptor *descriptor,
                      ImageState *state) {
    char path[4096];
    if (snprintf(path, sizeof path, "%s/%s/%s.patched.bin", directory,
                 descriptor->name, descriptor->name) >= (int)sizeof path) return 0;
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    if (fseek(file, 0, SEEK_END)) { fclose(file); return 0; }
    long size = ftell(file);
    if (size <= 0 || (uint64_t)size != descriptor->file_size ||
        size > 512L * 1024 * 1024 || fseek(file, 0, SEEK_SET)) {
        fclose(file);
        return 0;
    }
    state->size = (size_t)size;
    state->capacity = mng_symbol_index_capacity(descriptor->symbols.symbol_count);
    state->original = malloc(state->size);
    state->work = malloc(state->size);
    state->slots = calloc(state->capacity, sizeof *state->slots);
    size_t read = state->original ? fread(state->original, 1, state->size, file) : 0;
    int closed = fclose(file);
    return state->original && state->work && state->slots &&
           read == state->size && !closed;
}

static int save_image(const char *directory, const char *name,
                      const uint8_t *image, size_t size) {
    char path[4096];
    if (snprintf(path, sizeof path, "%s/%s.linked.bin", directory, name) >=
        (int)sizeof path) return 0;
    FILE *file = fopen(path, "wb");
    if (!file) return 0;
    size_t written = fwrite(image, 1, size, file);
    int closed = fclose(file);
    return written == size && !closed;
}

int main(int argc, char **argv) {
    if (argc != 4 || MNG_MODULE_COUNT < 1 || MNG_MODULE_COUNT > 16) return 2;
    char *end = NULL;
    unsigned long rounds = strtoul(argv[1], &end, 10);
    if (!end || *end || rounds < 2 || rounds > 20) return 2;
    ImageState images[MNG_MODULE_COUNT];
    MngLinkModule modules[MNG_MODULE_COUNT];
    MngGuestModule guests[MNG_MODULE_COUNT];
    memset(images, 0, sizeof images);
    memset(modules, 0, sizeof modules);
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index)
        if (!load_image(argv[2], &mng_modules[index], &images[index])) return 3;
    uint64_t prepare_first = 0, prepare_warm = UINT64_MAX;
    uint64_t link_first = 0, link_warm = UINT64_MAX;
    for (unsigned long round = 0; round < rounds; ++round) {
        uint64_t start = now_ns();
        for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
            ImageState *state = &images[index];
            memcpy(state->work, state->original, state->size);
            if (mng_modules[index].key_off >= UINT64_C(1) << 32 ||
                mng_link_prepare(&modules[index], &mng_modules[index], state->work,
                                 state->size, (uint64_t)(index + 1) << 32,
                                 state->slots, state->capacity)) return 4;
        }
        uint64_t elapsed = now_ns() - start;
        if (!round) prepare_first = elapsed;
        else if (elapsed < prepare_warm) prepare_warm = elapsed;
        size_t failed = 0;
        start = now_ns();
        int status = mng_link_all(modules, MNG_MODULE_COUNT, guests,
                                  MNG_MODULE_COUNT, NULL, NULL, &failed);
        elapsed = now_ns() - start;
        if (status) {
            fprintf(stderr, "link failed: status=%d module=%zu writes=%" PRIu64 "\n",
                    status, failed, modules[failed].applied_relocations);
            return 5;
        }
        if (!round) link_first = elapsed;
        else if (elapsed < link_warm) link_warm = elapsed;
    }
    printf("{\"rounds\":%lu,\"prepare_first_ns\":%" PRIu64
           ",\"prepare_warm_min_ns\":%" PRIu64 ",\"link_first_ns\":%" PRIu64
           ",\"link_warm_min_ns\":%" PRIu64 ",\"modules\":{",
           rounds, prepare_first, prepare_warm, link_first, link_warm);
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        MngLinkModule *module = &modules[index];
        if (!save_image(argv[3], module->descriptor->name,
                        module->image, module->image_size)) return 6;
        printf("%s\"%s\":{\"relocations\":%" PRIu64
               ",\"local\":%" PRIu64 ",\"global\":%" PRIu64
               ",\"weak_zero\":%" PRIu64 ",\"host\":%" PRIu64 "}",
               index ? "," : "", module->descriptor->name,
               module->applied_relocations, module->resolver.local,
               module->resolver.global, module->resolver.weak_zero,
               module->resolver.host_resolved);
    }
    puts("}}");
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        free(images[index].slots);
        free(images[index].work);
        free(images[index].original);
    }
    return 0;
}
