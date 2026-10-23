#pragma once

#include "module_link.h"

typedef struct {
    const MngModuleDescriptor *descriptor;
    uint8_t *bytes;
    size_t image_size, mapped_size;
    uint8_t sealed;
} MngMappedImage;

enum {
    MNG_IMAGE_OK = 0,
    MNG_IMAGE_INPUT = 1,
    MNG_IMAGE_HASH = 2,
    MNG_IMAGE_LAYOUT = 3,
    MNG_IMAGE_SYSTEM = 4,
};

/* macOS only. The caller zero-initializes image, then owns it until unmap.
 * Mapping is anonymous and writable for linking; no file handle is retained. */
int mng_image_map(MngMappedImage *image, const MngModuleDescriptor *descriptor,
                  const char *path);

/* Call only after mng_link_all succeeds for the complete module set. A failed
 * seal leaves image unusable; unmap it instead of executing any guest code. */
int mng_image_seal(MngMappedImage *image, const MngLinkModule *link);
void mng_image_unmap(MngMappedImage *image);
