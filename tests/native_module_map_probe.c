/* Offline macOS map/link/seal proof. Input and output paths are external. */
#include "module_image.h"
#include "module_gate.h"
#include "module-table.h"

#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef struct { uint64_t rx, ro, rw; } PageCounts;

static int check_permissions(const MngModuleDescriptor *desc,
                             const MngMappedImage *image, size_t page,
                             PageCounts *counts) {
    size_t rx_end = ((size_t)desc->text_end + page - 1) / page * page;
    size_t ro_end = (size_t)desc->data_off / page * page;
    for (size_t offset = 0; offset < image->mapped_size; offset += page) {
        int expected = offset < rx_end || offset >= desc->patch_off ?
            VM_PROT_READ | VM_PROT_EXECUTE :
            offset < ro_end || offset >= desc->key_off ? VM_PROT_READ :
            VM_PROT_READ | VM_PROT_WRITE;
        if (expected == (VM_PROT_READ | VM_PROT_EXECUTE)) ++counts->rx;
        else if (expected == VM_PROT_READ) ++counts->ro;
        else ++counts->rw;
        mach_vm_address_t address = (mach_vm_address_t)(uintptr_t)(image->bytes + offset);
        mach_vm_address_t region = address;
        mach_vm_size_t length = 0;
        vm_region_basic_info_data_64_t info;
        mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t object = MACH_PORT_NULL;
        kern_return_t status = mach_vm_region(mach_task_self(), &region, &length,
            VM_REGION_BASIC_INFO_64, (vm_region_info_t)&info, &count, &object);
        if (object != MACH_PORT_NULL) mach_port_deallocate(mach_task_self(), object);
        if (status != KERN_SUCCESS || region > address || length <= address - region ||
            info.protection != expected) {
            fprintf(stderr, "permission %s + %zu: expected=%d actual=%d status=%d\n",
                    desc->name, offset, expected,
                    status == KERN_SUCCESS ? info.protection : -1, status);
            return 0;
        }
    }
    return 1;
}

static uint64_t now_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) exit(2);
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + now.tv_nsec;
}

static const MngGateDescriptor *linear_gate(const MngMappedImage *images,
                                             uint64_t address, size_t *module_index) {
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        const MngModuleDescriptor *desc = images[index].descriptor;
        for (uint32_t gate = 0; gate < desc->gate_count; ++gate)
            if ((uintptr_t)images[index].bytes + desc->gates[gate].ret == address) {
                *module_index = index;
                return &desc->gates[gate];
            }
    }
    return NULL;
}

static int check_gates(const MngMappedImage *images, const MngGateTable *table,
                       uint64_t *gate_count, uint64_t *binary_min_ns,
                       uint64_t *linear_min_ns) {
    *gate_count = 0;
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        const MngModuleDescriptor *desc = images[index].descriptor;
        for (uint32_t gate = 0; gate < desc->gate_count; ++gate) {
            MngGateHit hit;
            uint64_t address = (uintptr_t)images[index].bytes + desc->gates[gate].ret;
            if (mng_gate_find(table, address, &hit) != MNG_GATE_FOUND ||
                hit.gate != &desc->gates[gate] || hit.module_index != index ||
                hit.module_base != (uintptr_t)images[index].bytes) return 0;
            ++*gate_count;
        }
        MngGateHit miss;
        if (mng_gate_find(table, (uintptr_t)images[index].bytes, &miss) !=
                MNG_GATE_MISSING || miss.gate ||
            mng_gate_find(table, (uintptr_t)images[index].bytes +
                              images[index].image_size - 1, &miss) !=
                MNG_GATE_MISSING || miss.gate) return 0;
    }
    if (!*gate_count) {
        *binary_min_ns = *linear_min_ns = 0;
        return 1;
    }
    *binary_min_ns = UINT64_MAX;
    *linear_min_ns = UINT64_MAX;
    volatile uint64_t binary_sum = 0, linear_sum = 0;
    for (unsigned round = 0; round < 7; ++round) {
        for (unsigned turn = 0; turn < 2; ++turn) {
            int binary = (round + turn) % 2 == 0;
            uint64_t start = now_ns();
            for (unsigned repeat = 0; repeat < 1000; ++repeat)
                for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
                    const MngModuleDescriptor *desc = images[index].descriptor;
                    for (uint32_t gate = 0; gate < desc->gate_count; ++gate) {
                        uint64_t address = (uintptr_t)images[index].bytes +
                                           desc->gates[gate].ret;
                        if (binary) {
                            MngGateHit hit;
                            if (mng_gate_find(table, address, &hit) != MNG_GATE_FOUND)
                                return 0;
                            binary_sum += hit.gate->arg + hit.module_index;
                        } else {
                            size_t found = 0;
                            const MngGateDescriptor *hit =
                                linear_gate(images, address, &found);
                            if (!hit) return 0;
                            linear_sum += hit->arg + found;
                        }
                    }
                }
            uint64_t elapsed = now_ns() - start;
            uint64_t *minimum = binary ? binary_min_ns : linear_min_ns;
            if (elapsed < *minimum) *minimum = elapsed;
        }
    }
    return binary_sum == linear_sum;
}

static int output_image(const char *folder, const MngModuleDescriptor *descriptor,
                        const MngMappedImage *image) {
    char path[4096];
    if (snprintf(path, sizeof path, "%s/%s.linked.bin", folder, descriptor->name) >=
        (int)sizeof path) return 0;
    FILE *stream = fopen(path, "wb");
    if (!stream) return 0;
    size_t count = fwrite(image->bytes, 1, image->image_size, stream);
    int closed = fclose(stream);
    return count == image->image_size && !closed;
}

int main(int argc, char **argv) {
    if (argc != 3 || MNG_MODULE_COUNT < 1 || MNG_MODULE_COUNT > 16) return 2;
    MngMappedImage images[MNG_MODULE_COUNT];
    MngLinkModule modules[MNG_MODULE_COUNT];
    MngGuestModule guests[MNG_MODULE_COUNT];
    uint32_t *slots[MNG_MODULE_COUNT];
    memset(images, 0, sizeof images);
    memset(modules, 0, sizeof modules);
    memset(slots, 0, sizeof slots);
    uint64_t start = now_ns();
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        const MngModuleDescriptor *desc = &mng_modules[index];
        char path[4096];
        if (snprintf(path, sizeof path, "%s/%s/%s.patched.bin", argv[1],
                     desc->name, desc->name) >= (int)sizeof path) return 3;
        int status = mng_image_map(&images[index], desc, path);
        if (status) {
            fprintf(stderr, "map %s: %d\n", desc->name, status);
            return 4;
        }
    }
    uint64_t map_ns = now_ns() - start;
    start = now_ns();
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        size_t capacity = mng_symbol_index_capacity(mng_modules[index].symbols.symbol_count);
        slots[index] = calloc(capacity, sizeof *slots[index]);
        if (!slots[index] || mng_link_prepare(&modules[index], &mng_modules[index],
               images[index].bytes, images[index].image_size,
               (uintptr_t)images[index].bytes, slots[index], capacity)) return 5;
    }
    uint64_t prepare_ns = now_ns() - start;
    size_t failed = 0;
    start = now_ns();
    int status = mng_link_all(modules, MNG_MODULE_COUNT, guests,
                              MNG_MODULE_COUNT, NULL, NULL, &failed);
    uint64_t link_ns = now_ns() - start;
    if (status) {
        fprintf(stderr, "link: %d at %zu\n", status, failed);
        return 6;
    }
    start = now_ns();
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        status = mng_image_seal(&images[index], &modules[index]);
        if (status) {
            fprintf(stderr, "seal %s: %d (text=%" PRIu64 " ro=%" PRIu64
                    " data=%" PRIu64 " key=%" PRIu64 " patch=%" PRIu64
                    " size=%" PRIu64 ")\n", mng_modules[index].name, status,
                    mng_modules[index].text_end, mng_modules[index].ro_off,
                    mng_modules[index].data_off, mng_modules[index].key_off,
                    mng_modules[index].patch_off, mng_modules[index].file_size);
            return 7;
        }
    }
    uint64_t seal_ns = now_ns() - start;
    long page_value = sysconf(_SC_PAGESIZE);
    if (page_value <= 0) return 9;
    PageCounts page_counts[MNG_MODULE_COUNT];
    memset(page_counts, 0, sizeof page_counts);
    start = now_ns();
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index)
        if (!check_permissions(&mng_modules[index], &images[index],
                               (size_t)page_value, &page_counts[index])) return 9;
    uint64_t permission_check_ns = now_ns() - start;
    MngGateTable gate_table = {0};
    if (mng_gate_table_build(&gate_table, images, MNG_MODULE_COUNT)) return 10;
    uint64_t gate_count, gate_binary_min_ns, gate_linear_min_ns;
    if (!check_gates(images, &gate_table, &gate_count,
                     &gate_binary_min_ns, &gate_linear_min_ns)) return 11;
    printf("{\"map_ns\":%" PRIu64 ",\"prepare_ns\":%" PRIu64
           ",\"link_ns\":%" PRIu64 ",\"seal_ns\":%" PRIu64
           ",\"permission_check_ns\":%" PRIu64 ",\"page_size\":%ld"
           ",\"gate_count\":%" PRIu64 ",\"gate_queries_per_round\":%" PRIu64
           ",\"gate_binary_min_ns\":%" PRIu64 ",\"gate_linear_min_ns\":%" PRIu64
           ",\"modules\":{", map_ns, prepare_ns, link_ns, seal_ns,
           permission_check_ns, page_value, gate_count, gate_count * 1000,
           gate_binary_min_ns, gate_linear_min_ns);
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        const MngModuleDescriptor *desc = &mng_modules[index];
        if (!output_image(argv[2], desc, &images[index])) return 8;
        printf("%s\"%s\":{\"base\":%" PRIu64 ",\"relocations\":%" PRIu64
               ",\"local\":%" PRIu64 ",\"global\":%" PRIu64
               ",\"weak_zero\":%" PRIu64 ",\"host\":%" PRIu64
               ",\"rx_pages\":%" PRIu64 ",\"ro_pages\":%" PRIu64
               ",\"rw_pages\":%" PRIu64 "}",
               index ? "," : "", desc->name, (uint64_t)(uintptr_t)images[index].bytes,
               modules[index].applied_relocations, modules[index].resolver.local,
               modules[index].resolver.global, modules[index].resolver.weak_zero,
               modules[index].resolver.host_resolved,
               page_counts[index].rx, page_counts[index].ro, page_counts[index].rw);
    }
    puts("}}");
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        mng_image_unmap(&images[index]);
        free(slots[index]);
    }
    return 0;
}
