#include "module_descriptor.h"

#include <string.h>

static int digest_valid(const char *digest) {
    if (!digest || strlen(digest) != 64) return 0;
    for (unsigned index = 0; index < 64; ++index) {
        char digit = digest[index];
        if (!((digit >= '0' && digit <= '9') || (digit >= 'a' && digit <= 'f')))
            return 0;
    }
    return digest[64] == 0;
}

int mng_module_descriptor_check(const MngModuleDescriptor *descriptor,
                                const uint8_t *image, size_t image_size,
                                uint64_t *relocation_count) {
    if (!descriptor || !image || !relocation_count || !descriptor->name ||
        !digest_valid(descriptor->sha256)) return MNG_DESCRIPTOR_INVALID;
    *relocation_count = 0;
    if (descriptor->file_size != image_size || !descriptor->text_end ||
        descriptor->text_end > descriptor->ro_off ||
        descriptor->ro_off > descriptor->data_off ||
        descriptor->data_off >= descriptor->key_off ||
        !descriptor->key_page_size ||
        descriptor->key_page_size > UINT64_MAX - descriptor->key_off ||
        descriptor->key_off + descriptor->key_page_size > descriptor->patch_off ||
        descriptor->patch_off > image_size ||
        descriptor->symbols.data_off != descriptor->data_off ||
        descriptor->symbols.key_off != descriptor->key_off ||
        descriptor->relocations.data_off != descriptor->data_off ||
        descriptor->relocations.key_off != descriptor->key_off ||
        descriptor->symbols.symbol_count != descriptor->relocations.symbol_count ||
        (descriptor->gate_count && !descriptor->gates)) return MNG_DESCRIPTOR_INVALID;
    MngSymbolView view;
    if (mng_symbol_open(&view, image, image_size, &descriptor->symbols) ||
        mng_reloc_walk(image, image_size, &descriptor->relocations,
                       NULL, NULL, relocation_count)) return MNG_DESCRIPTOR_INVALID;
    for (uint32_t index = 0; index < descriptor->gate_count; ++index) {
        const MngGateDescriptor *gate = &descriptor->gates[index];
        if (gate->ret % 4 || gate->ret < descriptor->patch_off ||
            gate->ret > image_size - 4 || gate->original % 4 ||
            gate->original >= descriptor->text_end ||
            !((gate->kind == MNG_GATE_SVC && gate->arg <= 0xffff) ||
              ((gate->kind == MNG_GATE_CNTPCT || gate->kind == MNG_GATE_CNTVCT) &&
               gate->arg <= 31))) return MNG_DESCRIPTOR_INVALID;
        if (index && descriptor->gates[index - 1].ret >= gate->ret)
            return MNG_DESCRIPTOR_INVALID;
    }
    return MNG_DESCRIPTOR_OK;
}
