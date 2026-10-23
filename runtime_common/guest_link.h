#pragma once

#include "symbol_view.h"

#include <stddef.h>
#include <stdint.h>

typedef struct {
    const MngSymbolView *symbols;
    uint64_t base;
} MngGuestModule;

/* Return 1 for a nonzero wrapped host address, 0 for no override, -1 for failure. */
typedef int (*MngGuestHostLookup)(void *context, const char *name, uint32_t kind,
                                  uint64_t *address);

typedef struct {
    const MngGuestModule *modules;
    size_t module_count, current;
    MngGuestHostLookup host;
    void *host_context;
    uint64_t local, global, weak_zero, host_resolved;
} MngGuestResolver;

enum {
    MNG_GUEST_OK = 0,
    MNG_GUEST_UNRESOLVED = 1,
    MNG_GUEST_FORMAT = 2,
    MNG_GUEST_HOST_ERROR = 3,
};

/* Matches the relocation resolver callback signature. All module indices
 * must be built first; each image and index must outlive the resolver. */
int mng_guest_resolve(void *context, uint32_t symbol, uint32_t kind,
                      uint64_t *address);
