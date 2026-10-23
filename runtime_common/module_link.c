#include "module_link.h"

#include "reloc_apply.h"

#include <string.h>

int mng_link_prepare(MngLinkModule *module, const MngModuleDescriptor *descriptor,
                     uint8_t *image, size_t image_size, uint64_t base,
                     uint32_t *slots, size_t slot_capacity) {
    if (!module) return MNG_LINK_INVALID;
    memset(module, 0, sizeof *module);
    if (!descriptor || !image || !slots ||
        descriptor->key_off > UINT64_MAX - base) return MNG_LINK_INVALID;
    size_t needed = mng_symbol_index_capacity(descriptor->symbols.symbol_count);
    if (!needed) return MNG_LINK_INVALID;
    if (slot_capacity < needed) return MNG_LINK_WORKSPACE;
    MngLinkModule ready = {.descriptor = descriptor, .image = image,
                           .image_size = image_size, .base = base};
    if (mng_module_descriptor_open(descriptor, image, image_size,
                                   &ready.symbols, &ready.expected_relocations) ||
        mng_symbol_index_build(&ready.symbols, slots, slot_capacity))
        return MNG_LINK_INVALID;
    *module = ready;
    return MNG_LINK_OK;
}

int mng_link_all(MngLinkModule *modules, size_t module_count,
                 MngGuestModule *guest_workspace, size_t guest_capacity,
                 MngGuestHostLookup host, void *host_context,
                 size_t *failed_index) {
    if (!failed_index) return MNG_LINK_INVALID;
    *failed_index = 0;
    if (!modules || !module_count || !guest_workspace || guest_capacity < module_count)
        return MNG_LINK_WORKSPACE;
    for (size_t index = 0; index < module_count; ++index) {
        MngLinkModule *module = &modules[index];
        if (!module->descriptor || !module->image ||
            module->symbols.image != module->image || !module->symbols.slots ||
            module->link_attempted ||
            module->base > UINT64_MAX - module->descriptor->key_off) {
            *failed_index = index;
            return MNG_LINK_INVALID;
        }
        guest_workspace[index] = (MngGuestModule){&module->symbols, module->base};
    }
    for (size_t index = 0; index < module_count; ++index)
        modules[index].link_attempted = 1;
    for (size_t index = 0; index < module_count; ++index) {
        MngLinkModule *module = &modules[index];
        module->resolver = (MngGuestResolver){.modules = guest_workspace,
            .module_count = module_count, .current = index,
            .host = host, .host_context = host_context};
        module->applied_relocations = 0;
        int status = mng_reloc_apply(module->image, module->image_size,
                                     &module->descriptor->relocations, module->base,
                                     mng_guest_resolve, &module->resolver,
                                     &module->applied_relocations);
        if (status || module->applied_relocations != module->expected_relocations) {
            *failed_index = index;
            return MNG_LINK_RELOCATION;
        }
    }
    for (size_t index = 0; index < module_count; ++index)
        modules[index].link_complete = 1;
    *failed_index = module_count;
    return MNG_LINK_OK;
}
