/* Offline equivalence and cost probe; all input and output paths stay external. */
#include "reloc_apply.h"

#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

_Static_assert(sizeof(MngReloc) == 24, "flat reference row width");

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

static uint8_t *read_file(const char *path, size_t limit, size_t *size) {
    FILE *file = fopen(path, "rb");
    if (!file || fseek(file, 0, SEEK_END)) return NULL;
    long length = ftell(file);
    if (length <= 0 || (uint64_t)length > limit || fseek(file, 0, SEEK_SET)) {
        fclose(file);
        return NULL;
    }
    uint8_t *data = malloc((size_t)length);
    size_t read_count = data ? fread(data, 1, (size_t)length, file) : 0;
    int closed = fclose(file);
    if (!data || read_count != (size_t)length || closed) {
        free(data);
        return NULL;
    }
    *size = (size_t)length;
    return data;
}

static uint64_t now_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) exit(2);
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

static int synthetic_resolve(void *context, uint32_t symbol, uint32_t kind,
                             uint64_t *address) {
    (void)context;
    if (kind != 257 && kind != 1025 && kind != 1026) return 1;
    *address = UINT64_C(0x200000000) + (uint64_t)symbol * 0x100;
    return 0;
}

static int apply_flat(uint8_t *image, const MngRelocLayout *layout,
                      const MngReloc *rows, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        const MngReloc *row = &rows[i];
        if (row->where % 8 || row->where < layout->data_off ||
            row->where > layout->key_off - 8 || row->symbol >= layout->symbol_count)
            return 1;
        uint64_t value;
        if (row->kind == 1027) {
            if (row->addend < 0 || (uint64_t)row->addend >= layout->key_off) return 1;
            value = UINT64_C(0x100000000) + (uint64_t)row->addend;
        } else {
            if (synthetic_resolve(NULL, row->symbol, row->kind, &value)) return 1;
            if (row->kind != 1026) value += (uint64_t)row->addend;
        }
        memcpy(image + row->where, &value, sizeof value);
    }
    return 0;
}

static uint64_t checksum(const uint8_t *data, size_t size) {
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < size; ++i)
        hash = (hash ^ data[i]) * UINT64_C(1099511628211);
    return hash;
}

int main(int argc, char **argv) {
    if (argc != 13) {
        fprintf(stderr, "usage: probe IMAGE FLAT DATA_OFF KEY_OFF NSYM RELR_OFF RELR_SIZE "
                        "RELA_OFF RELA_SIZE PLT_OFF PLT_SIZE ROUNDS\n");
        return 2;
    }
    size_t image_size = 0, flat_size = 0;
    uint8_t *original = read_file(argv[1], 512u * 1024u * 1024u, &image_size);
    uint8_t *flat_bytes = read_file(argv[2], 64u * 1024u * 1024u, &flat_size);
    if (!original || !flat_bytes || flat_size % 24) return 2;
    uint64_t symbols = number(argv[5]), rounds = number(argv[12]);
    if (!symbols || symbols > UINT32_MAX || rounds < 2 || rounds > 20) return 2;
    MngRelocLayout layout = {
        .data_off = number(argv[3]), .key_off = number(argv[4]),
        .symbol_count = (uint32_t)symbols,
        .relr_off = number(argv[6]), .relr_size = number(argv[7]),
        .rela_off = number(argv[8]), .rela_size = number(argv[9]),
        .plt_off = number(argv[10]), .plt_size = number(argv[11]),
    };
    if (layout.data_off >= layout.key_off || layout.key_off > image_size) return 2;
    uint8_t *stream_image = malloc(image_size), *flat_image = malloc(image_size);
    if (!stream_image || !flat_image) return 2;
    uint64_t stream_first = 0, flat_first = 0;
    uint64_t stream_warm_min = UINT64_MAX, flat_warm_min = UINT64_MAX;
    const MngReloc *rows = (const MngReloc *)flat_bytes;
    size_t row_count = flat_size / sizeof(*rows);
    for (uint64_t round = 0; round < rounds; ++round) {
        memcpy(stream_image, original, image_size);
        memcpy(flat_image, original, image_size);
        uint64_t stream_time, flat_time, start, applied = 0;
        int status;
        if (round % 2 == 0) {
            start = now_ns();
            status = mng_reloc_apply(stream_image, image_size, &layout,
                                     UINT64_C(0x100000000), synthetic_resolve,
                                     NULL, &applied);
            stream_time = now_ns() - start;
            if (status) return 1;
            start = now_ns();
            status = apply_flat(flat_image, &layout, rows, row_count);
            flat_time = now_ns() - start;
        } else {
            start = now_ns();
            status = apply_flat(flat_image, &layout, rows, row_count);
            flat_time = now_ns() - start;
            if (status) return 1;
            start = now_ns();
            status = mng_reloc_apply(stream_image, image_size, &layout,
                                     UINT64_C(0x100000000), synthetic_resolve,
                                     NULL, &applied);
            stream_time = now_ns() - start;
        }
        if (status || applied != row_count || memcmp(stream_image, flat_image, image_size)) {
            fprintf(stderr, "stream/flat mismatch in round %" PRIu64 "\n", round);
            return 1;
        }
        if (round == 0) {
            stream_first = stream_time;
            flat_first = flat_time;
        } else {
            if (stream_time < stream_warm_min) stream_warm_min = stream_time;
            if (flat_time < flat_warm_min) flat_warm_min = flat_time;
        }
    }
    uint64_t data_hash = checksum(stream_image + layout.data_off,
                                  (size_t)(layout.key_off - layout.data_off));
    printf("{\"count\":%zu,\"flat_bytes\":%zu,\"writable_checksum\":%" PRIu64
           ",\"stream_first_ns\":%" PRIu64 ",\"flat_first_ns\":%" PRIu64
           ",\"stream_warm_min_ns\":%" PRIu64 ",\"flat_warm_min_ns\":%" PRIu64
           ",\"rounds\":%" PRIu64 "}\n",
           row_count, flat_size, data_hash, stream_first, flat_first,
           stream_warm_min, flat_warm_min, rounds);
    free(stream_image);
    free(flat_image);
    free(flat_bytes);
    free(original);
    return 0;
}
