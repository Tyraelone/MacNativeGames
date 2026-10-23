#include "module_link.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { IMAGE_SIZE = 0x400 };

static void put32(uint8_t *image, size_t offset, uint32_t value) {
    memcpy(image + offset, &value, 4);
}

static void put64(uint8_t *image, size_t offset, uint64_t value) {
    memcpy(image + offset, &value, 8);
}

static uint64_t get64(const uint8_t *image, size_t offset) {
    uint64_t value;
    memcpy(&value, image + offset, 8);
    return value;
}

static void make_image(uint8_t *image, int sdk) {
    memset(image, 0, IMAGE_SIZE);
    memcpy(image + 0x60, "\0foo\0weak\0host\0", 15);
    for (unsigned index = 1; index < 4; ++index) {
        put32(image, 0x80 + 24 * index, index == 1 ? 1 : index == 2 ? 5 : 10);
        image[0x80 + 24 * index + 4] = index == 2 ? 0x20 : 0x10;
    }
    if (sdk) {
        image[0x80 + 24 + 6] = 1;
        put64(image, 0x80 + 24 + 8, 0x20);
    } else {
        const uint64_t where[] = {0x210, 0x218, 0x220, 0x228};
        const uint32_t kind[] = {1026, 1026, 1025, 1027};
        const uint32_t symbol[] = {1, 2, 3, 0};
        const uint64_t addend[] = {0, 0, 7, 0x30};
        for (unsigned index = 0; index < 4; ++index) {
            size_t at = 0x100 + index * 24;
            put64(image, at, where[index]);
            put64(image, at + 8, ((uint64_t)symbol[index] << 32) | kind[index]);
            put64(image, at + 16, addend[index]);
        }
    }
}

static MngModuleDescriptor descriptor(const char *name, int sdk) {
    MngModuleDescriptor module = {
        .name = name, .sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        .file_size = IMAGE_SIZE, .text_end = 0x40, .ro_off = 0x40,
        .data_off = 0x200, .key_off = 0x300,
        .key_page_size = 0x80, .patch_off = 0x380,
        .symbols = {.data_off = 0x200, .key_off = 0x300, .str_off = 0x60,
                    .str_size = 15, .sym_off = 0x80, .symbol_count = 4},
        .relocations = {.data_off = 0x200, .key_off = 0x300,
                        .rela_off = sdk ? 0 : 0x100, .rela_size = sdk ? 0 : 96,
                        .symbol_count = 4},
    };
    return module;
}

static int host(void *context, const char *name, uint32_t kind, uint64_t *address) {
    (void)kind;
    if (strcmp(name, "host")) return 0;
    if (context) return -1;
    *address = 0x7000;
    return 1;
}

static int run(const char *mode) {
    uint8_t main_image[IMAGE_SIZE], sdk_image[IMAGE_SIZE];
    make_image(main_image, 0);
    make_image(sdk_image, 1);
    MngModuleDescriptor main_desc = descriptor("main", 0), sdk_desc = descriptor("sdk", 1);
    MngLinkModule modules[2] = {0};
    uint32_t main_slots[16], sdk_slots[16];
    MngGuestModule guests[2];
    if (!strcmp(mode, "invalid")) {
        if (mng_link_prepare(&modules[0], &main_desc, main_image, IMAGE_SIZE,
                             UINT64_C(0x100000000), main_slots, 8) != MNG_LINK_WORKSPACE)
            return 1;
        main_desc.relocations.rela_off = main_desc.data_off;
        return mng_link_prepare(&modules[0], &main_desc, main_image, IMAGE_SIZE,
                                UINT64_C(0x100000000), main_slots, 16) == MNG_LINK_INVALID ? 0 : 2;
    }
    if (mng_link_prepare(&modules[0], &main_desc, main_image, IMAGE_SIZE,
                         UINT64_C(0x100000000), main_slots, 16)) return 3;
    if (!strcmp(mode, "unprepared")) {
        size_t failed = 99;
        if (mng_link_all(modules, 2, guests, 2, host, NULL, &failed) != MNG_LINK_INVALID ||
            get64(main_image, 0x210) || failed != 1) return 4;
        return 0;
    }
    if (mng_link_prepare(&modules[1], &sdk_desc, sdk_image, IMAGE_SIZE,
                         UINT64_C(0x200000000), sdk_slots, 16)) return 5;
    size_t failed = 99;
    int result = mng_link_all(modules, 2, guests, 2, host,
                              !strcmp(mode, "host_error") ? (void *)1 : NULL, &failed);
    if (!strcmp(mode, "host_error")) {
        int retry = mng_link_all(modules, 2, guests, 2, host, NULL, &failed);
        return result == MNG_LINK_RELOCATION && retry == MNG_LINK_INVALID && failed == 0 &&
               !modules[0].link_complete && !modules[1].link_complete &&
               modules[0].applied_relocations == 2 &&
               get64(main_image, 0x210) == UINT64_C(0x200000020) &&
               get64(main_image, 0x220) == 0 ? 0 : 6;
    }
    if (strcmp(mode, "success") || result || failed != 2) return 7;
    int retry = mng_link_all(modules, 2, guests, 2, host, NULL, &failed);
    return retry == MNG_LINK_INVALID && failed == 0 &&
           modules[0].link_complete && modules[1].link_complete &&
           modules[0].applied_relocations == 4 && modules[1].applied_relocations == 0 &&
           modules[0].resolver.global == 1 && modules[0].resolver.weak_zero == 1 &&
           modules[0].resolver.host_resolved == 1 &&
           get64(main_image, 0x210) == UINT64_C(0x200000020) &&
           get64(main_image, 0x218) == 0 && get64(main_image, 0x220) == 0x7007 &&
           get64(main_image, 0x228) == UINT64_C(0x100000030) ? 0 : 8;
}

int main(int argc, char **argv) {
    return argc == 2 ? run(argv[1]) : 9;
}
