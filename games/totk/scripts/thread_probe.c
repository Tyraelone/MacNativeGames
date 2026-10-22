/* Host-thread and kernel synchronization tests, using the production dispatcher. */
#include "../runtime/runtime.h"
#include <stdatomic.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <mach/mach_time.h>
#include <unistd.h>
static atomic_uint calls,environments;
static atomic_uint pause_calls, pause_stop;
static atomic_uint blocker_started, blocker_stop, resumed_waiter_ran;
_Noreturn void runtime_fail(const char *message){fprintf(stderr,"FAIL %s\n",message);exit(1);}
void *runtime_symbol(const char *name){(void)name;runtime_fail("unexpected guest symbol");}
void runtime_thread_init(void){atomic_fetch_add(&environments,1);}
uint64_t runtime_now_ns(void){mach_timebase_info_data_t t;mach_timebase_info(&t);return (uint64_t)((__uint128_t)mach_absolute_time()*t.numer/t.denom);}
static void need(int c,const char *m){if(!c)runtime_fail(m);}
static void kernel(unsigned id,uint64_t *r){need(svc_thread((int)id,r)==1,"service dispatch");}
static void child(uint64_t arg){atomic_fetch_add(&calls,1);uint64_t r[31]={arg};kernel(0x11,r);need(r[0]==0,"child signal");kernel(0x0a,r);runtime_fail("ExitThread returned");}
static void pause_child(uint64_t arg){
 (void)arg;
 while(!atomic_load(&pause_stop)){
  atomic_fetch_add(&pause_calls,1);
  uint64_t r[31]={1000000};kernel(0x0b,r);
 }
 uint64_t r[31]={0};kernel(0x0a,r);runtime_fail("paused child ExitThread returned");
}
static void core_blocker(uint64_t arg){
 (void)arg;atomic_store(&blocker_started,1);
 while(!atomic_load(&blocker_stop)) sched_yield();
 uint64_t r[31]={0};kernel(0x0a,r);runtime_fail("core blocker ExitThread returned");
}
static void core_waiter(uint64_t arg){
 (void)arg;atomic_store(&resumed_waiter_ran,1);
 uint64_t r[31]={0};kernel(0x0a,r);runtime_fail("core waiter ExitThread returned");
}
int main(void){
 uint32_t main=svc_thread_main_init();uint64_t r[31]={0};r[1]=main;kernel(0xc,r);need(r[0]==0&&r[1]==44,"initial priority");
 r[0]=main;r[1]=31;kernel(0xd,r);r[1]=main;kernel(0xc,r);need(r[0]==0&&r[1]==31,"priority roundtrip");
 r[1]=7;kernel(0xc,r);need(r[0]==0xe401,"bad handle query");r[0]=7;kernel(0x16,r);need(r[0]==0xe401,"bad handle close");
 unsigned count=0;
 for(unsigned i=0;i<32;i++){
  kernel(0x45,r);need(!r[0],"event create");uint32_t write=(uint32_t)r[1],read=(uint32_t)r[2];
  r[0]=read;kernel(0x11,r);need(r[0]==0xe401,"reject signaling read handle");
  r[1]=(uintptr_t)&read;r[2]=1;r[3]=0;kernel(0x18,r);need(r[0]==0xea01,"unsignaled event timeout");
  uint8_t *stack=mmap(NULL,2<<20,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);need(stack!=MAP_FAILED,"guest stack");
  r[1]=(uintptr_t)child;r[2]=write;r[3]=(uintptr_t)stack+(2<<20);r[4]=44;r[5]=0;kernel(8,r);need(!r[0],"thread create");uint32_t thread=(uint32_t)r[1];
  unsigned before=atomic_load(&calls);r[0]=thread;kernel(9,r);need(!r[0],"thread start");
  r[1]=(uintptr_t)&read;r[2]=1;r[3]=1000000000;kernel(0x18,r);need(!r[0]&&r[1]==0,"event wait");
  r[1]=(uintptr_t)&thread;r[2]=1;r[3]=1000000000;kernel(0x18,r);need(!r[0],"wait thread exit");need(atomic_load(&calls)==before+1,"child ran exactly once");
  r[0]=read;kernel(0x17,r);need(!r[0],"event reset");r[0]=read;kernel(0x17,r);need(r[0]==0xfa01,"second reset fails");
  r[0]=thread;kernel(0x16,r);need(!r[0],"close thread");r[0]=read;kernel(0x16,r);need(!r[0],"close read");r[0]=write;kernel(0x16,r);need(!r[0],"close write");
  need(munmap(stack,2<<20)==0,"reclaim guest stack after exit wait");
  count++;
 }
 need(atomic_load(&environments)==32,"per-thread setup");
 uint8_t *pause_stack=mmap(NULL,2<<20,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);need(pause_stack!=MAP_FAILED,"pause guest stack");
 r[1]=(uintptr_t)pause_child;r[2]=0;r[3]=(uintptr_t)pause_stack+(2<<20);r[4]=44;r[5]=1;kernel(8,r);need(!r[0],"pause thread create");uint32_t pause_thread=(uint32_t)r[1];
 r[0]=pause_thread;kernel(9,r);need(!r[0],"pause thread start");
 usleep(20000);need(atomic_load(&pause_calls)>0,"pause thread ran");
 r[0]=pause_thread;r[1]=1;kernel(0x32,r);need(!r[0],"pause thread activity");
 usleep(20000);unsigned held=atomic_load(&pause_calls);usleep(20000);need(atomic_load(&pause_calls)==held,"paused thread must stop");
 _Alignas(16) uint8_t context[0x320]={0};r[0]=(uintptr_t)context;r[1]=pause_thread;kernel(0x33,r);need(!r[0],"get paused thread context");
 uint64_t sp=0,pc=0;__builtin_memcpy(&sp,context+0xf8,8);__builtin_memcpy(&pc,context+0x100,8);need(sp&&pc,"paused context has stack and PC");
 r[0]=pause_thread;r[1]=0;kernel(0x32,r);need(!r[0],"resume thread activity");
 atomic_store(&pause_stop,1);r[1]=(uintptr_t)&pause_thread;r[2]=1;r[3]=1000000000;kernel(0x18,r);need(!r[0],"resumed thread exited");
 r[0]=pause_thread;kernel(0x16,r);need(!r[0],"close paused thread");need(munmap(pause_stack,2<<20)==0,"reclaim pause guest stack");
 /* A paused waiter can be the only user of a virtual core. Resume must
    notice that the core is already free, even without a future core_put. */
 r[0]=main;r[1]=1;r[2]=2;kernel(0x0f,r);need(!r[0],"move main to core 1");
 uint8_t *block_stack=mmap(NULL,2<<20,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
 uint8_t *wait_stack=mmap(NULL,2<<20,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
 need(block_stack!=MAP_FAILED&&wait_stack!=MAP_FAILED,"core wait probe stacks");
 r[1]=(uintptr_t)core_blocker;r[2]=0;r[3]=(uintptr_t)block_stack+(2<<20);r[4]=44;r[5]=0;
 kernel(8,r);need(!r[0],"create core blocker");uint32_t blocker=(uint32_t)r[1];
 r[0]=blocker;kernel(9,r);need(!r[0],"start core blocker");
 for(int i=0;i<1000&&!atomic_load(&blocker_started);i++)usleep(1000);
 need(atomic_load(&blocker_started),"core blocker ran");
 r[1]=(uintptr_t)core_waiter;r[2]=0;r[3]=(uintptr_t)wait_stack+(2<<20);r[4]=44;r[5]=0;
 kernel(8,r);need(!r[0],"create core waiter");uint32_t waiter=(uint32_t)r[1];
 r[0]=waiter;kernel(9,r);need(!r[0],"start core waiter");
 usleep(20000);need(!atomic_load(&resumed_waiter_ran),"waiter blocked on occupied core");
 r[0]=waiter;r[1]=1;kernel(0x32,r);need(!r[0],"pause queued core waiter");
 atomic_store(&blocker_stop,1);r[1]=(uintptr_t)&blocker;r[2]=1;r[3]=1000000000;
 kernel(0x18,r);need(!r[0],"core blocker exited");
 r[0]=waiter;r[1]=0;kernel(0x32,r);need(!r[0],"resume queued core waiter");
 r[1]=(uintptr_t)&waiter;r[2]=1;r[3]=1000000000;kernel(0x18,r);
 need(!r[0]&&atomic_load(&resumed_waiter_ran),"resumed waiter acquired idle core");
 r[0]=waiter;kernel(0x16,r);need(!r[0],"close core waiter");
 r[0]=blocker;kernel(0x16,r);need(!r[0],"close core blocker");
 need(!munmap(block_stack,2<<20)&&!munmap(wait_stack,2<<20),"reclaim core probe stacks");
 printf("{\"status\":\"pass\",\"native_threads\":%u,\"events\":%u,\"scope\":\"production SVC dispatcher, host stack switching, event/thread waits, priority and invalid handles\"}\n",count,count);return 0;
}
