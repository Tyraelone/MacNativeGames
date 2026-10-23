#include "guest_link.h"

#include <stdint.h>

static int module_address(const MngGuestModule *module, uint64_t value,
                          uint64_t *address) {
    if (value >= module->symbols->layout.key_off || module->base > UINT64_MAX - value)
        return MNG_GUEST_FORMAT;
    *address = module->base + value;
    return MNG_GUEST_OK;
}

int mng_guest_resolve(void *context, uint32_t symbol, uint32_t kind,
                      uint64_t *address) {
    MngGuestResolver *resolver = context;
    if (!resolver || !resolver->modules || !resolver->module_count ||
        resolver->current >= resolver->module_count || !address ||
        (kind != 257 && kind != 1025 && kind != 1026))
        return MNG_GUEST_FORMAT;
    const MngGuestModule *current = &resolver->modules[resolver->current];
    if (!current->symbols || !current->symbols->image ||
        !current->symbols->slots || symbol >= current->symbols->layout.symbol_count)
        return MNG_GUEST_FORMAT;
    MngSymbol entry;
    if (mng_symbol_at(current->symbols, symbol, &entry)) return MNG_GUEST_FORMAT;
    if (resolver->host) {
        uint64_t host_address = 0;
        int found = resolver->host(resolver->host_context, entry.name, kind, &host_address);
        if (found < 0) return MNG_GUEST_HOST_ERROR;
        if (found > 0 && host_address) {
            *address = host_address;
            ++resolver->host_resolved;
            return MNG_GUEST_OK;
        }
    }
    if (entry.defined && entry.binding != 2) {
        if (entry.value >= current->symbols->layout.key_off) return MNG_GUEST_UNRESOLVED;
        int status = module_address(current, entry.value, address);
        if (!status) ++resolver->local;
        return status;
    }
    for (size_t index = 0; index < resolver->module_count; ++index) {
        const MngGuestModule *module = &resolver->modules[index];
        if (!module->symbols || !module->symbols->image || !module->symbols->slots)
            return MNG_GUEST_FORMAT;
        uint32_t found_index = 0;
        int found = mng_symbol_lookup(module->symbols, entry.name, &found_index);
        if (found < 0) return MNG_GUEST_FORMAT;
        if (!found) continue;
        MngSymbol definition;
        if (mng_symbol_at(module->symbols, found_index, &definition)) return MNG_GUEST_FORMAT;
        int status = module_address(module, definition.value, address);
        if (!status) ++resolver->global;
        return status;
    }
    if (entry.binding == 2) {
        *address = 0;
        ++resolver->weak_zero;
        return MNG_GUEST_OK;
    }
    return MNG_GUEST_UNRESOLVED;
}
