#include "module_descriptor.h"
#include "module-table.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int run(const char *root, int reject_invalid) {
    putchar('{');
    for (size_t index = 0; index < MNG_MODULE_COUNT; ++index) {
        const MngModuleDescriptor *module = &mng_modules[index];
        char path[4096];
        if (snprintf(path, sizeof path, "%s/%s/%s.patched.bin", root,
                     module->name, module->name) >= (int)sizeof path) return 2;
        FILE *stream = fopen(path, "rb");
        if (!stream) return 3;
        uint8_t *image = malloc((size_t)module->file_size);
        if (!image) { fclose(stream); return 4; }
        size_t size = fread(image, 1, (size_t)module->file_size, stream);
        int extra = fgetc(stream);
        fclose(stream);
        uint64_t relocations = 0;
        int status = size == module->file_size && extra == EOF &&
                     !mng_module_descriptor_check(module, image, size, &relocations);
        if (status && reject_invalid) {
            MngModuleDescriptor invalid = *module;
            uint64_t ignored = 0;
            invalid.file_size++;
            status = mng_module_descriptor_check(&invalid, image, size, &ignored) != 0;
            invalid = *module;
            invalid.symbols.str_off = invalid.data_off;
            status = status && mng_module_descriptor_check(&invalid, image, size, &ignored) != 0;
            invalid = *module;
            invalid.relocations.rela_off = invalid.data_off;
            status = status && mng_module_descriptor_check(&invalid, image, size, &ignored) != 0;
            MngGateDescriptor gate = {.ret = 0, .kind = MNG_GATE_SVC};
            invalid = *module;
            invalid.gates = &gate;
            invalid.gate_count = 1;
            status = status && mng_module_descriptor_check(&invalid, image, size, &ignored) != 0;
            if (module->gate_count >= 2) {
                MngGateDescriptor unordered[2] = {module->gates[1], module->gates[0]};
                invalid.gates = unordered;
                invalid.gate_count = 2;
                status = status &&
                    mng_module_descriptor_check(&invalid, image, size, &ignored) != 0;
            }
        }
        free(image);
        if (!status) return 5;
        if (index) putchar(',');
        printf("\"%s\":{\"symbols\":%u,\"relocations\":%llu,\"gates\":%u}",
               module->name, module->symbols.symbol_count,
               (unsigned long long)relocations, module->gate_count);
    }
    puts("}");
    return 0;
}

int main(int argc, char **argv) {
    return (argc == 2 || (argc == 3 && !strcmp(argv[2], "reject-invalid"))) ?
        run(argv[1], argc == 3) : 1;
}
