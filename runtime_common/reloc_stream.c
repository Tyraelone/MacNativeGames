#include "reloc_stream.h"

#include <limits.h>
#include <string.h>

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Switch and Apple ARM64 relocation tables require a little-endian host"
#endif

static uint64_t read_u64(const uint8_t *address) {
    uint64_t value;
    memcpy(&value, address, sizeof value);
    return value;
}

static int source_table(uint64_t offset, uint64_t size, uint64_t data_off,
                        uint64_t entry_size) {
    if (size % entry_size) return MNG_RELOC_FORMAT;
    if (size && (offset > data_off || size > data_off - offset)) return MNG_RELOC_BOUNDS;
    return MNG_RELOC_OK;
}

static int emit(const uint8_t *image, const MngRelocLayout *layout,
                const MngReloc *row, MngRelocVisit visit, void *context,
                uint64_t *count) {
    if (row->where % 8 || row->where < layout->data_off ||
        row->where > layout->key_off - 8 || row->symbol >= layout->symbol_count)
        return MNG_RELOC_BOUNDS;
    if (row->kind != 257 && row->kind != 1025 && row->kind != 1026 && row->kind != 1027)
        return MNG_RELOC_FORMAT;
    if (row->kind == 1027 && (row->addend < 0 || (uint64_t)row->addend >= layout->key_off))
        return MNG_RELOC_BOUNDS;
    (void)image;
    ++*count;
    if (visit && visit(context, row)) return MNG_RELOC_VISITOR;
    return MNG_RELOC_OK;
}

static int walk_rela(const uint8_t *image, const MngRelocLayout *layout,
                     uint64_t offset, uint64_t size, MngRelocVisit visit,
                     void *context, uint64_t *count) {
    for (uint64_t at = offset; at < offset + size; at += 24) {
        uint64_t info = read_u64(image + at + 8);
        MngReloc row = {
            .where = read_u64(image + at),
            .kind = (uint32_t)info,
            .symbol = (uint32_t)(info >> 32),
            .addend = (int64_t)read_u64(image + at + 16),
        };
        int status = emit(image, layout, &row, visit, context, count);
        if (status) return status;
    }
    return MNG_RELOC_OK;
}

static int walk_relr(const uint8_t *image, const MngRelocLayout *layout,
                     MngRelocVisit visit, void *context, uint64_t *count) {
    uint64_t cursor = 0;
    int have_cursor = 0;
    for (uint64_t at = layout->relr_off; at < layout->relr_off + layout->relr_size; at += 8) {
        uint64_t entry = read_u64(image + at);
        if (!(entry & 1)) {
            if (entry > UINT64_MAX - 8) return MNG_RELOC_BOUNDS;
            MngReloc row = {.where = entry, .kind = 1027, .symbol = 0};
            if (entry > layout->key_off - 8 || entry < layout->data_off || entry % 8)
                return MNG_RELOC_BOUNDS;
            row.addend = (int64_t)read_u64(image + entry);
            int status = emit(image, layout, &row, visit, context, count);
            if (status) return status;
            cursor = entry + 8;
            have_cursor = 1;
        } else {
            if (!have_cursor || cursor > UINT64_MAX - 63 * 8) return MNG_RELOC_FORMAT;
            for (unsigned bit = 1; bit < 64; ++bit) {
                if (!(entry & ((uint64_t)1 << bit))) continue;
                uint64_t where = cursor + (uint64_t)(bit - 1) * 8;
                if (where > layout->key_off - 8 || where < layout->data_off || where % 8)
                    return MNG_RELOC_BOUNDS;
                MngReloc row = {.where = where, .kind = 1027, .symbol = 0,
                                .addend = (int64_t)read_u64(image + where)};
                int status = emit(image, layout, &row, visit, context, count);
                if (status) return status;
            }
            cursor += 63 * 8;
        }
    }
    return MNG_RELOC_OK;
}

int mng_reloc_walk(const uint8_t *image, size_t image_size,
                   const MngRelocLayout *layout, MngRelocVisit visit,
                   void *context, uint64_t *count) {
    if (!count) return MNG_RELOC_FORMAT;
    *count = 0;
    if (!image || !layout || !layout->symbol_count ||
        layout->data_off >= layout->key_off || layout->key_off > image_size ||
        layout->key_off < 8 || layout->key_off > INT64_MAX)
        return MNG_RELOC_BOUNDS;
    int status = source_table(layout->relr_off, layout->relr_size, layout->data_off, 8);
    if (status) return status;
    status = source_table(layout->rela_off, layout->rela_size, layout->data_off, 24);
    if (status) return status;
    status = source_table(layout->plt_off, layout->plt_size, layout->data_off, 24);
    if (status) return status;
    status = walk_relr(image, layout, visit, context, count);
    if (status) return status;
    status = walk_rela(image, layout, layout->rela_off, layout->rela_size, visit, context, count);
    if (status) return status;
    return walk_rela(image, layout, layout->plt_off, layout->plt_size, visit, context, count);
}
