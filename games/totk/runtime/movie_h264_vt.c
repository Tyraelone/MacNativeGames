/* H.264 movie::Decoder backend for the Switch game's Annex-B samples.
   VideoToolbox decodes into a macOS NV12 pixel buffer; copy row by row into
   the packed NV12 layout expected by the existing movie::Decoder adapter. */
#include "movie_h264_vt.h"
#include <CoreMedia/CoreMedia.h>
#include <CoreVideo/CoreVideo.h>
#include <VideoToolbox/VideoToolbox.h>
#include <stdlib.h>
#include <string.h>

struct H264Host {
    CMVideoFormatDescriptionRef format;
    VTDecompressionSessionRef session;
    CVPixelBufferRef frame;
    CMTime frame_pts;
    int width, height, error;
};

static int start_code(const uint8_t *p, size_t n) {
    if (n >= 4 && !p[0] && !p[1] && !p[2] && p[3] == 1) return 4;
    if (n >= 3 && !p[0] && !p[1] && p[2] == 1) return 3;
    return 0;
}
static size_t next_start(const uint8_t *p, size_t n, size_t from) {
    for (size_t i = from; i + 3 <= n; i++) if (start_code(p + i, n - i)) return i;
    return n;
}
static void output(void *ref, void *frame_ref, OSStatus status, VTDecodeInfoFlags info,
                   CVImageBufferRef image, CMTime pts, CMTime duration) {
    (void)frame_ref;(void)info;(void)duration;
    H264Host *h=ref;
    if (status || !image || CFGetTypeID(image) != CVPixelBufferGetTypeID()) { h->error=status?status:-1; return; }
    if (h->frame) CVPixelBufferRelease(h->frame);
    h->frame=(CVPixelBufferRef)CFRetain(image);h->frame_pts=pts;
}
static int make_session(H264Host *h) {
    int fmt=kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange;
    CFNumberRef number=CFNumberCreate(kCFAllocatorDefault,kCFNumberIntType,&fmt);
    const void *keys[]={kCVPixelBufferPixelFormatTypeKey};const void *values[]={number};
    CFDictionaryRef attrs=CFDictionaryCreate(kCFAllocatorDefault,keys,values,1,
        &kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    VTDecompressionOutputCallbackRecord callback={output,h};
    OSStatus st=VTDecompressionSessionCreate(kCFAllocatorDefault,h->format,NULL,attrs,&callback,&h->session);
    CFRelease(attrs);CFRelease(number);
    return st==noErr?0:-1;
}
H264Host *h264_host_create(const uint8_t *sps,size_t sn,const uint8_t *pps,size_t pn,int w,int h) {
    int a=start_code(sps,sn),b=start_code(pps,pn);
    if (!a || !b || sn<=(size_t)a || pn<=(size_t)b || w<=0 || h<=0 || (w|h)&1) return NULL;
    const uint8_t *sets[]={sps+a,pps+b};size_t sizes[]={sn-(size_t)a,pn-(size_t)b};
    H264Host *host=calloc(1,sizeof *host);if (!host) return NULL;
    host->width=w;host->height=h;
    OSStatus st=CMVideoFormatDescriptionCreateFromH264ParameterSets(kCFAllocatorDefault,2,sets,sizes,4,&host->format);
    if (st || make_session(host)) { h264_host_destroy(host);return NULL; }
    return host;
}
static int avcc_packet(const uint8_t *src,size_t n,uint8_t *dst,size_t cap) {
    if (!start_code(src,n)) { memcpy(dst,src,n);return (int)n; }
    size_t i=0,o=0;
    while (i<n) {
        int code=start_code(src+i,n-i);if (!code) return -1;
        size_t begin=i+(size_t)code,end=next_start(src,n,begin);
        if (end<=begin || end-begin>UINT32_MAX || o+4+end-begin>cap) return -1;
        uint32_t len=(uint32_t)(end-begin);
        dst[o++]=(uint8_t)(len>>24);dst[o++]=(uint8_t)(len>>16);
        dst[o++]=(uint8_t)(len>>8);dst[o++]=(uint8_t)len;
        memcpy(dst+o,src+begin,len);o+=len;i=end;
    }
    return (int)o;
}
int h264_host_decode(H264Host *h,const uint8_t *packet,size_t n,int64_t pts_us,
                     uint8_t *dst,size_t cap,int64_t *out_pts) {
    if (!h || !packet || !n || !dst || !out_pts || n>INT32_MAX) return -1;
    size_t need=(size_t)h->width*h->height*3/2;if (cap<need) return -1;
    uint8_t *avcc=malloc(n*2);if (!avcc) return -1;
    int bytes=avcc_packet(packet,n,avcc,n*2);if (bytes<=0) {free(avcc);return -1;}
    CMBlockBufferRef block=NULL;CMSampleBufferRef sample=NULL;
    OSStatus st=CMBlockBufferCreateWithMemoryBlock(kCFAllocatorDefault,NULL,(size_t)bytes,
        kCFAllocatorDefault,NULL,0,(size_t)bytes,0,&block);
    if (!st) st=CMBlockBufferReplaceDataBytes(avcc,block,0,(size_t)bytes);
    free(avcc);
    size_t sample_size=(size_t)bytes;
    if (!st) st=CMSampleBufferCreateReady(kCFAllocatorDefault,block,h->format,1,0,NULL,1,&sample_size,&sample);
    if (block) CFRelease(block);
    if (st) {if(sample)CFRelease(sample);return -1;}
    CMSampleBufferSetOutputPresentationTimeStamp(sample,CMTimeMake(pts_us,1000000));
    h->error=0;
    st=VTDecompressionSessionDecodeFrame(h->session,sample,0,NULL,NULL);
    if (!st) st=VTDecompressionSessionWaitForAsynchronousFrames(h->session);
    CFRelease(sample);
    if (st || h->error) return -1;
    if (!h->frame) return 0;
    CVPixelBufferRef frame=h->frame;h->frame=NULL;
    if (CVPixelBufferLockBaseAddress(frame,kCVPixelBufferLock_ReadOnly)) {CVPixelBufferRelease(frame);return -1;}
    int ok=CVPixelBufferGetPlaneCount(frame)==2 &&
        CVPixelBufferGetWidth(frame)==(size_t)h->width && CVPixelBufferGetHeight(frame)==(size_t)h->height;
    if (ok) {
        for (int y=0;y<h->height;y++)
            memcpy(dst+(size_t)y*h->width,(uint8_t *)CVPixelBufferGetBaseAddressOfPlane(frame,0)+(size_t)y*CVPixelBufferGetBytesPerRowOfPlane(frame,0),(size_t)h->width);
        for (int y=0;y<h->height/2;y++)
            memcpy(dst+(size_t)h->width*h->height+(size_t)y*h->width,(uint8_t *)CVPixelBufferGetBaseAddressOfPlane(frame,1)+(size_t)y*CVPixelBufferGetBytesPerRowOfPlane(frame,1),(size_t)h->width);
        *out_pts=CMTimeConvertScale(h->frame_pts,1000000,kCMTimeRoundingMethod_Default).value;
    }
    CVPixelBufferUnlockBaseAddress(frame,kCVPixelBufferLock_ReadOnly);CVPixelBufferRelease(frame);
    return ok?1:-1;
}
int h264_host_flush(H264Host *h) {
    if (!h) return -1;
    VTDecompressionSessionInvalidate(h->session);CFRelease(h->session);h->session=NULL;
    if (h->frame) {CVPixelBufferRelease(h->frame);h->frame=NULL;}
    return make_session(h);
}
void h264_host_destroy(H264Host *h) {
    if (!h) return;
    if (h->session) {VTDecompressionSessionInvalidate(h->session);CFRelease(h->session);}
    if (h->frame) CVPixelBufferRelease(h->frame);
    if (h->format) CFRelease(h->format);
    free(h);
}
