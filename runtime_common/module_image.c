#include "module_image.h"

#if !defined(__APPLE__)
#error "Native module mapping requires macOS"
#endif

#include <CommonCrypto/CommonDigest.h>
#include <libkern/OSCacheControl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

#include <limits.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>

static size_t page_size(void) {
    long value = sysconf(_SC_PAGESIZE);
    return value > 0 ? (size_t)value : 0;
}

static int round_up(size_t value, size_t page, size_t *result) {
    if (!page || value > SIZE_MAX - (page - 1)) return 0;
    *result = (value + page - 1) / page * page;
    return 1;
}

static int valid_digest(const char *digest) {
    if (!digest || strlen(digest) != 64) return 0;
    for (unsigned index = 0; index < 64; ++index)
        if (!((digest[index] >= '0' && digest[index] <= '9') ||
              (digest[index] >= 'a' && digest[index] <= 'f'))) return 0;
    return 1;
}

void mng_image_unmap(MngMappedImage *image) {
    if (!image) return;
    if (image->bytes && image->mapped_size)
        munmap(image->bytes, image->mapped_size);
    memset(image, 0, sizeof *image);
}

int mng_image_map(MngMappedImage *image, const MngModuleDescriptor *descriptor,
                  const char *path) {
    if (!image || image->bytes || !descriptor || !path ||
        !valid_digest(descriptor->sha256) ||
        !descriptor->file_size || descriptor->file_size > SIZE_MAX)
        return MNG_IMAGE_INPUT;
    memset(image, 0, sizeof *image);
    size_t size = (size_t)descriptor->file_size, mapped_size, page = page_size();
    if (!round_up(size, page, &mapped_size)) return MNG_IMAGE_INPUT;
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return errno == ELOOP ? MNG_IMAGE_INPUT : MNG_IMAGE_SYSTEM;
    struct stat stat_before, stat_after;
    int status = MNG_IMAGE_SYSTEM;
    void *bytes = MAP_FAILED;
    if (fstat(fd, &stat_before)) goto done;
    if (!S_ISREG(stat_before.st_mode) || stat_before.st_size < 0 ||
        (uint64_t)stat_before.st_size != descriptor->file_size) {
        status = MNG_IMAGE_INPUT;
        goto done;
    }
    bytes = mmap(NULL, mapped_size, PROT_READ | PROT_WRITE,
                 MAP_PRIVATE | MAP_ANON, -1, 0);
    if (bytes == MAP_FAILED) goto done;
    size_t offset = 0;
    while (offset < size) {
        ssize_t count = read(fd, (uint8_t *)bytes + offset, size - offset);
        if (count < 0 && errno == EINTR) continue;
        if (!count) {
            status = MNG_IMAGE_INPUT;
            goto done;
        }
        if (count < 0) goto done;
        offset += (size_t)count;
    }
    if (fstat(fd, &stat_after)) goto done;
    if (stat_after.st_dev != stat_before.st_dev ||
        stat_after.st_ino != stat_before.st_ino ||
        stat_after.st_size != stat_before.st_size) {
        status = MNG_IMAGE_INPUT;
        goto done;
    }
    CC_SHA256_CTX hash;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    char hex[CC_SHA256_DIGEST_LENGTH * 2 + 1];
    CC_SHA256_Init(&hash);
    for (size_t at = 0; at < size;) {
        size_t count = size - at;
        if (count > 1024 * 1024) count = 1024 * 1024;
        CC_SHA256_Update(&hash, (uint8_t *)bytes + at, (CC_LONG)count);
        at += count;
    }
    CC_SHA256_Final(digest, &hash);
    static const char digits[] = "0123456789abcdef";
    for (unsigned index = 0; index < CC_SHA256_DIGEST_LENGTH; ++index) {
        hex[index * 2] = digits[digest[index] >> 4];
        hex[index * 2 + 1] = digits[digest[index] & 15];
    }
    hex[64] = 0;
    if (strcmp(hex, descriptor->sha256)) {
        status = MNG_IMAGE_HASH;
        goto done;
    }
    *image = (MngMappedImage){.descriptor = descriptor, .bytes = bytes,
                               .image_size = size, .mapped_size = mapped_size};
    bytes = MAP_FAILED;
    status = MNG_IMAGE_OK;
done:
    if (bytes != MAP_FAILED) munmap(bytes, mapped_size);
    close(fd);
    return status;
}

int mng_image_seal(MngMappedImage *image, const MngLinkModule *link) {
    if (!image || !image->bytes || image->sealed || !image->descriptor || !link ||
        !link->link_complete || link->descriptor != image->descriptor ||
        link->image != image->bytes || link->image_size != image->image_size ||
        link->base != (uintptr_t)image->bytes ||
        link->applied_relocations != link->expected_relocations)
        return MNG_IMAGE_INPUT;
    const MngModuleDescriptor *desc = image->descriptor;
    size_t page = page_size(), rx_end, patch_end;
    if (!page || desc->file_size != image->image_size ||
        !desc->text_end || desc->text_end > desc->ro_off ||
        desc->ro_off > desc->data_off || desc->data_off >= desc->key_off ||
        !desc->key_page_size || desc->key_page_size > UINT64_MAX - desc->key_off ||
        desc->key_off + desc->key_page_size > desc->patch_off ||
        desc->patch_off > desc->file_size ||
        desc->key_off % page ||
        (desc->patch_off < desc->file_size && desc->patch_off % page) ||
        !round_up((size_t)desc->text_end, page, &rx_end) ||
        !round_up(image->image_size, page, &patch_end))
        return MNG_IMAGE_LAYOUT;
    size_t ro_end = (size_t)desc->data_off / page * page;
    if (rx_end > ro_end || ro_end > desc->key_off ||
        patch_end != image->mapped_size) return MNG_IMAGE_LAYOUT;
    if (mprotect(image->bytes, rx_end, PROT_READ | PROT_EXEC) ||
        (ro_end > rx_end &&
         mprotect(image->bytes + rx_end, ro_end - rx_end, PROT_READ)) ||
        mprotect(image->bytes + desc->key_off,
                 (desc->patch_off == desc->file_size ? patch_end :
                  (size_t)desc->patch_off) - (size_t)desc->key_off, PROT_READ) ||
        (desc->patch_off < desc->file_size &&
         mprotect(image->bytes + desc->patch_off,
                  patch_end - desc->patch_off, PROT_READ | PROT_EXEC)))
        return MNG_IMAGE_SYSTEM;
    sys_icache_invalidate(image->bytes, rx_end);
    if (desc->patch_off < desc->file_size)
        sys_icache_invalidate(image->bytes + desc->patch_off,
                              patch_end - desc->patch_off);
    image->sealed = 1;
    return MNG_IMAGE_OK;
}
