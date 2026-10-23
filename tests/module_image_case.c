#include "module_image.h"

#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

static int permissions(const uint8_t *address) {
    mach_vm_address_t region = (mach_vm_address_t)(uintptr_t)address;
    mach_vm_size_t size = 0;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object = MACH_PORT_NULL;
    kern_return_t status = mach_vm_region(mach_task_self(), &region, &size,
        VM_REGION_BASIC_INFO_64, (vm_region_info_t)&info, &count, &object);
    if (object != MACH_PORT_NULL) mach_port_deallocate(mach_task_self(), object);
    return status == KERN_SUCCESS ? info.protection : -1;
}

int main(int argc, char **argv) {
    if (argc != 4) return 90;
    MngModuleDescriptor desc = {
        .name = "synthetic", .sha256 = argv[2],
        .file_size = 0x14000, .text_end = 0x4000, .ro_off = 0x4000,
        .data_off = 0x8000, .key_off = 0xc000, .key_page_size = 0x4000,
        .patch_off = 0x10000,
        .symbols = {.data_off = 0x8000, .key_off = 0xc000,
                    .str_off = 0x4000, .str_size = 1,
                    .sym_off = 0x4100, .symbol_count = 1},
        .relocations = {.data_off = 0x8000, .key_off = 0xc000, .symbol_count = 1},
    };
    if (!strcmp(argv[3], "size")) ++desc.file_size;
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    if (!strcmp(argv[3], "sharedpage")) {
        desc.text_end = 0x4000 - page / 4;
        desc.ro_off = 0x4000 - page / 8;
        desc.data_off = 0x8000 + page / 4;
        desc.symbols.data_off = desc.data_off;
        desc.relocations.data_off = desc.data_off;
    }
    if (!strcmp(argv[3], "wx_overlap")) {
        desc.text_end = 0x8000 + page / 4;
        desc.ro_off = desc.text_end;
        desc.data_off = desc.text_end + page / 4;
        desc.symbols.data_off = desc.data_off;
        desc.relocations.data_off = desc.data_off;
    }
    if (!strcmp(argv[3], "nopatch")) desc.patch_off = desc.file_size;
    MngMappedImage image = {0};
    int status = mng_image_map(&image, &desc, argv[1]);
    if (!strcmp(argv[3], "hash") || !strcmp(argv[3], "size") ||
        !strcmp(argv[3], "symlink")) {
        int expected = !strcmp(argv[3], "hash") ? MNG_IMAGE_HASH : MNG_IMAGE_INPUT;
        return status == expected && !image.bytes && !image.mapped_size ? 0 : 1;
    }
    if (status || image.image_size != desc.file_size ||
        image.mapped_size != 0x14000 || image.bytes[0] != 0x5a) return 2;
    uint32_t slots[16];
    MngLinkModule link = {0};
    MngGuestModule guest;
    size_t failed = 99;
    if (mng_image_seal(&image, &link) == MNG_IMAGE_OK) return 3;
    if (mng_link_prepare(&link, &desc, image.bytes, image.image_size,
                         (uintptr_t)image.bytes, slots, 16)) return 4;
    if (mng_image_seal(&image, &link) == MNG_IMAGE_OK) return 5;
    if (mng_link_all(&link, 1, &guest, 1, NULL, NULL, &failed) || failed != 1)
        return 6;
    if (!strcmp(argv[3], "layout") || !strcmp(argv[3], "wx_overlap")) {
        if (!strcmp(argv[3], "layout")) desc.patch_off++;
        if (mng_image_seal(&image, &link) == MNG_IMAGE_OK ||
            permissions(image.bytes) != (VM_PROT_READ | VM_PROT_WRITE)) return 7;
        mng_image_unmap(&image);
        return image.bytes || image.mapped_size ? 8 : 0;
    }
    if (mng_image_seal(&image, &link) || !image.sealed) return 9;
    if (permissions(image.bytes) != (VM_PROT_READ | VM_PROT_EXECUTE) ||
        permissions(image.bytes + 0x4000) != VM_PROT_READ ||
        permissions(image.bytes + 0x8000) != (VM_PROT_READ | VM_PROT_WRITE) ||
        permissions(image.bytes + 0xc000) != VM_PROT_READ ||
        permissions(image.bytes + 0x10000) !=
            (!strcmp(argv[3], "nopatch") ? VM_PROT_READ :
             VM_PROT_READ | VM_PROT_EXECUTE)) return 10;
    if (!strcmp(argv[3], "sharedpage") &&
        (permissions(image.bytes + desc.ro_off) != (VM_PROT_READ | VM_PROT_EXECUTE) ||
         permissions(image.bytes + 0x8000) != (VM_PROT_READ | VM_PROT_WRITE))) return 13;
    if (mng_image_seal(&image, &link) == MNG_IMAGE_OK) return 11;
    mng_image_unmap(&image);
    return image.bytes || image.mapped_size || image.sealed ? 12 : 0;
}
