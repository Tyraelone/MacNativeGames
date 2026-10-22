/* audout:u direct PCM output, using the libnx audout.c IPC layout. */
#include "runtime.h"
#include "ipc.h"
#include <AudioToolbox/AudioToolbox.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct OutBuf { struct OutBuf *next; uint64_t tag; uint8_t *pcm; size_t bytes, pos; } OutBuf;
typedef struct {
    pthread_mutex_t lock;
    AudioComponentInstance unit;
    uint32_t event, rate, channels;
    int started, unit_ok;
    float volume;
    OutBuf *head, *tail;
    uint64_t released[256], played;
    unsigned rd, wr, queued;
} AudioOut;
static void need(int ok,const char *msg){if(!ok){fprintf(stderr,"[totk-audout] %s\n",msg);runtime_fail("audio output protocol");}}
static IpcBuffer input(const IpcRequest *q){return q->na&&q->a[0].size?q->a[0]:q->nx?q->x[0]:(IpcBuffer){0};}
static IpcBuffer output(const IpcRequest *q){return q->nb&&q->b[0].size?q->b[0]:q->nc?q->c[0]:(IpcBuffer){0};}
static void release(AudioOut *a,OutBuf *b){
    need(a->wr-a->rd<256,"released queue full");
    a->released[a->wr++&255]=b->tag;a->queued--;
    runtime_event_signal(a->event);free(b->pcm);free(b);
}
static OSStatus pull(void *ctx,AudioUnitRenderActionFlags *flags,const AudioTimeStamp *ts,UInt32 bus,UInt32 frames,AudioBufferList *io){
    (void)flags;(void)ts;(void)bus;
    AudioOut *a=ctx;float *dst=io->mBuffers[0].mData;
    memset(dst,0,(size_t)frames*2*sizeof(float));
    pthread_mutex_lock(&a->lock);
    for(UInt32 i=0;i<frames&&a->started;i++){
        while(a->head&&a->head->pos>=a->head->bytes){
            OutBuf *b=a->head;a->head=b->next;if(!a->head)a->tail=NULL;release(a,b);
        }
        if(!a->head)continue;
        const int16_t *p=(const int16_t *)(a->head->pcm+a->head->pos);
        float l=p[0]/32768.0f,r=a->channels==1?l:p[1]/32768.0f;
        if(a->channels==6){l+=0.7071f*(p[2]+p[4])/32768.0f;r+=0.7071f*(p[2]+p[5])/32768.0f;}
        dst[2*i]=l*a->volume;dst[2*i+1]=r*a->volume;
        a->head->pos+=(size_t)a->channels*2;a->played++;
    }
    pthread_mutex_unlock(&a->lock);return noErr;
}
static void open_unit(AudioOut *a){
    AudioComponentDescription d={kAudioUnitType_Output,kAudioUnitSubType_DefaultOutput,kAudioUnitManufacturer_Apple,0,0};
    AudioComponent c=AudioComponentFindNext(NULL,&d);
    need(c&&AudioComponentInstanceNew(c,&a->unit)==noErr,"CoreAudio output device");
    AudioStreamBasicDescription f={(Float64)a->rate,kAudioFormatLinearPCM,kAudioFormatFlagIsFloat|kAudioFormatFlagIsPacked,8,1,8,2,32,0};
    AURenderCallbackStruct cb={pull,a};
    need(AudioUnitSetProperty(a->unit,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Input,0,&f,sizeof f)==noErr&&
         AudioUnitSetProperty(a->unit,kAudioUnitProperty_SetRenderCallback,kAudioUnitScope_Input,0,&cb,sizeof cb)==noErr&&
         AudioUnitInitialize(a->unit)==noErr,"CoreAudio stream setup");
    a->unit_ok=1;fprintf(stderr,"[totk-audout] CoreAudio %u Hz x%u\n",a->rate,a->channels);
}
static void close_out(void *state){
    AudioOut *a=state;if(!a)return;
    if(a->unit_ok){AudioOutputUnitStop(a->unit);AudioUnitUninitialize(a->unit);AudioComponentInstanceDispose(a->unit);}
    while(a->head){OutBuf *b=a->head;a->head=b->next;free(b->pcm);free(b);}
    pthread_mutex_destroy(&a->lock);free(a);
}
static void out_handler(IpcSession *s,const IpcRequest *q,IpcResponse *r){
    AudioOut *a=s->state;
    static unsigned traced;if(traced++<32)fprintf(stderr,"[totk-audout] cmd=%u data=%u a=%u x=%u b=%u c=%u in=%#llx+%#llx\n",q->cmd,q->data_size,q->na,q->nx,q->nb,q->nc,(unsigned long long)input(q).addr,(unsigned long long)input(q).size);
    switch(q->cmd){
    case 0:{uint32_t x=a->started?0:1;IPC_OUT(r,x);return;}
    case 1:
        if(!a->unit_ok)open_unit(a);
        pthread_mutex_lock(&a->lock);a->started=1;pthread_mutex_unlock(&a->lock);
        need(AudioOutputUnitStart(a->unit)==noErr,"CoreAudio start");return;
    case 2:
        if(a->unit_ok)AudioOutputUnitStop(a->unit);
        pthread_mutex_lock(&a->lock);a->started=0;pthread_mutex_unlock(&a->lock);return;
    case 3:case 7:{
        IpcBuffer in=input(q);need(q->data_size>=8&&in.size>=0x28,"AppendAudioOutBuffer arguments");
        uint64_t tag=IPC_ARG(q,uint64_t,0);
        const uint64_t *d=ipc_guest(in.addr,0x28);
        uint64_t address=d[1],capacity=d[2],size=d[3],offset=d[4];
        need(size<=capacity&&offset<=capacity-size&&size<=16*1024*1024&&size%((uint64_t)a->channels*2)==0,"AppendAudioOutBuffer size");
        OutBuf *b=calloc(1,sizeof *b);need(b!=NULL,"buffer allocation");
        b->pcm=malloc(size?size:1);need(b->pcm!=NULL,"PCM allocation");
        if(size)memcpy(b->pcm,ipc_guest(address+offset,size),size);
        b->bytes=(size_t)size;b->tag=tag;
        pthread_mutex_lock(&a->lock);
        if(a->tail)a->tail->next=b;else a->head=b;
        a->tail=b;a->queued++;
        pthread_mutex_unlock(&a->lock);return;
    }
    case 4:r->copy[r->ncopy++]=runtime_event_readable(a->event);return;
    case 5:case 8:{
        IpcBuffer out=output(q);need(out.size>=8,"GetReleasedAudioOutBuffers output");
        uint64_t *p=ipc_guest(out.addr,out.size);uint32_t n=0,cap=(uint32_t)(out.size/8);
        pthread_mutex_lock(&a->lock);
        while(n<cap&&a->rd!=a->wr)p[n++]=a->released[a->rd++&255];
        pthread_mutex_unlock(&a->lock);IPC_OUT(r,n);
        if(q->nc&&!q->nb)r->xout[r->nxout++]=(IpcBuffer){out.addr,out.size,0};
        return;
    }
    case 6:{
        uint64_t tag=IPC_ARG(q,uint64_t,0);uint8_t found=0;
        pthread_mutex_lock(&a->lock);
        for(OutBuf *b=a->head;b;b=b->next)if(b->tag==tag){found=1;break;}
        pthread_mutex_unlock(&a->lock);IPC_OUT(r,found);return;
    }
    case 9:{uint32_t n;pthread_mutex_lock(&a->lock);n=a->queued;pthread_mutex_unlock(&a->lock);IPC_OUT(r,n);return;}
    case 10:{uint64_t n;pthread_mutex_lock(&a->lock);n=a->played;pthread_mutex_unlock(&a->lock);IPC_OUT(r,n);return;}
    case 11:{
        pthread_mutex_lock(&a->lock);uint8_t had=a->head!=NULL;
        while(a->head){OutBuf *b=a->head;a->head=b->next;release(a,b);}
        a->tail=NULL;pthread_mutex_unlock(&a->lock);IPC_OUT(r,had);return;
    }
    case 12:{float v=IPC_ARG(q,float,0);pthread_mutex_lock(&a->lock);a->volume=v;pthread_mutex_unlock(&a->lock);return;}
    case 13:{float v;pthread_mutex_lock(&a->lock);v=a->volume;pthread_mutex_unlock(&a->lock);IPC_OUT(r,v);return;}
    default:ipc_unimplemented(s,q);
    }
}
static void manager_handler(IpcSession *s,const IpcRequest *q,IpcResponse *r){
    switch(q->cmd){
    case 0:case 2:{
        IpcBuffer out=output(q);need(out.size>=0x100,"ListAudioOuts output");
        char *p=ipc_guest(out.addr,out.size);memset(p,0,0x100);memcpy(p,"DeviceOut",9);
        uint32_t count=1;IPC_OUT(r,count);
        if(q->nc&&!q->nb)r->xout[r->nxout++]=(IpcBuffer){out.addr,out.size,0};return;
    }
    case 1:case 3:{
        need(q->has_pid&&q->ncopy==1&&q->data_size>=16,"OpenAudioOut arguments");
        uint32_t rate=IPC_ARG(q,uint32_t,0),packed=IPC_ARG(q,uint32_t,4);
        fprintf(stderr,"[totk-audout] requested rate=%u channel field=%#x\n",rate,packed);
        AudioOut *a=calloc(1,sizeof *a);need(a!=NULL,"AudioOut allocation");
        a->rate=rate?rate:48000;a->channels=packed&0xffff;
        if(!a->channels)a->channels=2;
        need((a->rate==48000||a->rate==32000)&&(a->channels==1||a->channels==2||a->channels==6),"unsupported PCM format");
        a->event=runtime_event_new();a->volume=1.0f;pthread_mutex_init(&a->lock,NULL);
        IpcBuffer name=output(q);
        if(name.size>=0x100){char *p=ipc_guest(name.addr,name.size);memset(p,0,0x100);memcpy(p,"DeviceOut",9);}
        uint32_t out[4]={a->rate,a->channels,2,1};ipc_out(r,out,sizeof out);
        if(q->nc&&!q->nb&&name.size)r->xout[r->nxout++]=(IpcBuffer){name.addr,name.size,0};
        r->move[r->nmove++]=runtime_ipc_new_session("IAudioOut",out_handler,a,close_out);
        fprintf(stderr,"[totk-audout] open %u Hz x%u\n",a->rate,a->channels);return;
    }
    default:ipc_unimplemented(s,q);
    }
}
__attribute__((constructor)) static void register_audio_out(void){runtime_ipc_register("audout:u",manager_handler,NULL,NULL);}
