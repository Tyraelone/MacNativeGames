#ifndef TOTK_MOVIE_H264_VT_H
#define TOTK_MOVIE_H264_VT_H
#include <stddef.h>
#include <stdint.h>

typedef struct H264Host H264Host;
H264Host *h264_host_create(const uint8_t *sps, size_t sps_size,
                           const uint8_t *pps, size_t pps_size, int width, int height);
/* Returns one decoded NV12 frame, zero for decoder delay, or a negative error. */
int h264_host_decode(H264Host *host, const uint8_t *packet, size_t size,
                     int64_t pts_us, uint8_t *nv12, size_t capacity, int64_t *output_pts_us);
int h264_host_flush(H264Host *host);
void h264_host_destroy(H264Host *host);
#endif
