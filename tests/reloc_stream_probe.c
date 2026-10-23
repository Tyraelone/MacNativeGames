#include "reloc_stream.h"

#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

typedef struct {
    uint64_t kinds[4];
    uint64_t checksum;
} Probe;

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

static int visit(void *context, const MngReloc *row) {
    Probe *probe = context;
    unsigned index = row->kind == 257 ? 0 : row->kind == 1025 ? 1 :
                     row->kind == 1026 ? 2 : 3;
    probe->kinds[index]++;
    probe->checksum = (probe->checksum * UINT64_C(1099511628211)) ^
                      row->where ^ ((uint64_t)row->kind << 32) ^
                      row->symbol ^ (uint64_t)row->addend;
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 12) {
        fprintf(stderr, "usage: probe IMAGE DATA_OFF KEY_OFF NSYM RELR_OFF RELR_SIZE "
                        "RELA_OFF RELA_SIZE PLT_OFF PLT_SIZE ROUNDS\n");
        return 2;
    }
    FILE *file = fopen(argv[1], "rb");
    if (!file || fseek(file, 0, SEEK_END)) return 2;
    long length = ftell(file);
    if (length < 0 || length > 512L * 1024 * 1024 || fseek(file, 0, SEEK_SET)) return 2;
    uint8_t *image = malloc((size_t)length);
    if (!image || fread(image, 1, (size_t)length, file) != (size_t)length || fclose(file)) return 2;
    uint64_t symbols = number(argv[4]), rounds = number(argv[11]);
    if (symbols == 0 || symbols > UINT32_MAX || rounds == 0 || rounds > 20) return 2;
    MngRelocLayout layout = {
        .data_off = number(argv[2]), .key_off = number(argv[3]), .symbol_count = (uint32_t)symbols,
        .relr_off = number(argv[5]), .relr_size = number(argv[6]),
        .rela_off = number(argv[7]), .rela_size = number(argv[8]),
        .plt_off = number(argv[9]), .plt_size = number(argv[10]),
    };
    uint64_t first_ns = 0, warm_min_ns = UINT64_MAX;
    Probe final = {0};
    uint64_t final_count = 0;
    for (uint64_t i = 0; i < rounds; ++i) {
        Probe current = {0};
        uint64_t count = 0, start = now_ns();
        int status = mng_reloc_walk(image, (size_t)length, &layout, visit, &current, &count);
        uint64_t duration = now_ns() - start;
        if (status) {
            fprintf(stderr, "relocation walk failed: %d after %" PRIu64 " records\n", status, count);
            free(image);
            return 1;
        }
        if (i == 0) first_ns = duration;
        else if (duration < warm_min_ns) warm_min_ns = duration;
        final = current;
        final_count = count;
    }
    printf("{\"count\":%" PRIu64 ",\"kinds\":{\"257\":%" PRIu64
           ",\"1025\":%" PRIu64 ",\"1026\":%" PRIu64 ",\"1027\":%" PRIu64
           "},\"checksum\":%" PRIu64 ",\"first_ns\":%" PRIu64
           ",\"warm_min_ns\":%" PRIu64 ",\"rounds\":%" PRIu64 "}\n",
           final_count, final.kinds[0], final.kinds[1], final.kinds[2], final.kinds[3],
           final.checksum, first_ns, rounds > 1 ? warm_min_ns : 0, rounds);
    free(image);
    return 0;
}
