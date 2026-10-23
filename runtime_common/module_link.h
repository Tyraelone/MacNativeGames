#pragma once

#include "guest_link.h"
#include "module_descriptor.h"

typedef struct {
    const MngModuleDescriptor *descriptor;
    uint8_t *image;
    size_t image_size;
    uint64_t base;
    MngSymbolView symbols;
    uint64_t expected_relocations, applied_relocations;
    MngGuestResolver resolver;
    uint8_t link_attempted;
} MngLinkModule;

enum {
    MNG_LINK_OK = 0,
    MNG_LINK_INVALID = 1,
    MNG_LINK_WORKSPACE = 2,
    MNG_LINK_RELOCATION = 3,
};

/* The caller must verify image SHA-256 against descriptor->sha256 first.
 * Slots are caller-owned and must outlive the prepared module. */
int mng_link_prepare(MngLinkModule *module, const MngModuleDescriptor *descriptor,
                     uint8_t *image, size_t image_size, uint64_t base,
                     uint32_t *slots, size_t slot_capacity);

/* Validates every prepared module before writing. Link is one-shot even on
 * failure; discard all images and reload verified originals before a retry.
 * guest_workspace has at least module_count rows and is caller-owned. */
int mng_link_all(MngLinkModule *modules, size_t module_count,
                 MngGuestModule *guest_workspace, size_t guest_capacity,
                 MngGuestHostLookup host, void *host_context,
                 size_t *failed_index);
