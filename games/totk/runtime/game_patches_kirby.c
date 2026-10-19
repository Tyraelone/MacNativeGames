/* Kirby Star Allies experimental profile: no game-code patches yet.
   The SDK 4.4 game is started unmodified; output-size and frame-step probes
   are kept as no-ops so the shared runtime can link. */
#include "game_patches.h"
#include "game_version.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <mach/mach.h>
#include "mach_vm_compat.h"
void runtime_describe_address(uint64_t a, char *out, size_t n);

void runtime_game_patches(Module *main_module) {
    (void)main_module;
    fprintf(stderr, "[kirby] no game-code patches applied\n");
}
int runtime_output_res(unsigned *w, unsigned *h) { (void)w; (void)h; return 0; }
uint64_t runtime_output_res_extra_bytes(void) { return 0; }
int runtime_output_res_toggle(void) { return 0; }
int runtime_output_mode_cycle(void) { return 0; }
void runtime_frame_step_pin(double ms) { (void)ms; }
void runtime_frame_step_update(uint64_t now_ns) { (void)now_ns; }

/* Diagnostic entry hook on the SDK's variadic AbortImpl. It prints the
   file/function/line/expression and the assertion format string before the
   guest stops. The literal branch keeps x0..x7 untouched. */
static void kirby_abort_probe(const char *file, const char *func, const char *expr, int line,
                              const void *result, const void *info, const char *fmt, ...) {
    fprintf(stderr, "[kirby-abort] file=%.160s\n[kirby-abort] func=%.160s\n[kirby-abort] expr=%.200s\n[kirby-abort] line=%d result=%p info=%p fmt=%.240s\n",
            file ? file : "(null)", func ? func : "(null)", expr ? expr : "(null)", line, result, info, fmt ? fmt : "(null)");
    fflush(stderr);
    _exit(70);
}

static void kirby_trap_probe(uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3,
                             uint64_t x4, uint64_t x5, uint64_t x6, uint64_t x7) {
    uint64_t regs[8] = {x0, x1, x2, x3, x4, x5, x6, x7};
    fprintf(stderr, "[kirby-trap] x0..x7:");
    for (unsigned i = 0; i < 8; i++) fprintf(stderr, " %#llx", (unsigned long long)regs[i]);
    fputc('\n', stderr);
    for (unsigned i = 0; i < 8; i++) {
        uint8_t buf[128] = {0}; mach_vm_size_t got = 0;
        if (regs[i] > 0x10000 && mach_vm_read_overwrite(mach_task_self(), regs[i], sizeof buf, (uintptr_t)buf, &got) == KERN_SUCCESS && got == sizeof buf) {
            fprintf(stderr, "[kirby-trap] x%u bytes:", i);
            for (unsigned k = 0; k < 32; k++) fprintf(stderr, " %02x", buf[k]);
            fputc('\n', stderr);
            unsigned n = 0; while (n < 100 && buf[n] >= 0x20 && buf[n] < 0x7f) n++;
            if (n >= 4) fprintf(stderr, "[kirby-trap] x%u str=%.100s\n", i, (char *)buf);
        }
    }
    if (x2) {
        uint64_t tab[16] = {0}; mach_vm_size_t got = 0;
        if (mach_vm_read_overwrite(mach_task_self(), x2, sizeof tab, (uintptr_t)tab, &got) == KERN_SUCCESS && got == sizeof tab) {
            for (unsigned i = 0; i < 16; i++) {
                char where[128] = {0};
                runtime_describe_address(tab[i], where, sizeof where);
                fprintf(stderr, "[kirby-trap] x2[%u] %#llx %s\n", i, (unsigned long long)tab[i], where);
            }
        }
    }
    fflush(stderr);
    _exit(72);
}

/* SDK 4.4's account::CloseUser dispatches through a service object that the
   host does not implement. The user handle is only closed on the failed path
   here; skipping the close lets the game continue without an invalid object. */
void runtime_kirby_sdk_patches(Module *m) {
    if (strcmp(m->name, "sdk")) return;
    uint32_t *close_user = (uint32_t *)(void *)(m->base + 0xb3530);
    if (*close_user == 0xF9400800u) {   /* ldr x0,[x0,#0x10] */
        *close_user = 0xD65F03C0u;      /* ret */
        fprintf(stderr, "[kirby] patched sdk account::CloseUser to return\n");
    }
    /* The SDK account object is never created because nn::account::Initialize
       is answered by the host. Return a zero user handle instead of following
       the null service virtual call. */
    uint32_t *open_user = (uint32_t *)(void *)(m->base + 0xb3478);
    if (open_user[0] != 0xA9007C1Fu) {
        open_user[0] = 0xA9007C1Fu;      /* stp xzr,xzr,[x0] */
        open_user[1] = 0x2A1F03E0u;      /* mov w0,wzr */
        open_user[2] = 0xD65F03C0u;      /* ret */
        fprintf(stderr, "[kirby] patched sdk account::OpenPreselectedUser to return a zero handle (was %08x)\n", open_user[0]);
    }
    /* AbortImpl can be entered through a function pointer that skips the
       first word; put the probe in the module's patch area and branch to it
       from all three plausible entry points. */
    uint32_t *stub = (uint32_t *)(void *)(m->base + m->patch_off);
    stub[0] = 0x58000050u;              /* ldr x16, #8 */
    stub[1] = 0xD61F0200u;              /* br x16 */
    memcpy(&stub[2], &(uintptr_t){(uintptr_t)kirby_abort_probe}, 8);
    for (unsigned k = 0; k < 3; k++) {
        uint32_t off = 0x444a8u + 4u * k;
        int64_t delta = (int64_t)m->patch_off - (int64_t)off;
        ((uint32_t *)(void *)(m->base + off))[0] = 0x14000000u | ((uint32_t)((delta >> 2) & 0x3ffffffu));
    }
    if (getenv("KIRBY_PATCH_DIAG")) {
        uint32_t *diag = (uint32_t *)(void *)(m->base + 0x452c4);
        if (diag[0] != 0xD65F03C0u) { diag[0] = 0xD65F03C0u; fprintf(stderr, "[kirby] patched sdk diag translate to return\n"); }
    }
    fprintf(stderr, "[kirby] sdk AbortImpl hooks installed at 0x444a8..0x444b0 -> patch+%#llx host=%p\n",
            (unsigned long long)m->patch_off, (void *)kirby_abort_probe);
    /* The generic abort trap ends in an infinite branch. In this experimental
       profile, return instead so an asserting worker can unwind and the scene
       can continue; the svcBreak handler already logs the assertion. */
    uint32_t *trap_spin = (uint32_t *)(void *)(m->base + 0x456dc);
    if (*trap_spin == 0x14000000u) {
        *trap_spin = 0xD65F03C0u;   /* ret */
        fprintf(stderr, "[kirby] patched sdk abort trap spin to return\n");
    }
    if (getenv("KIRBY_TRAP_PROBE")) {
        uint32_t *trap_stub = (uint32_t *)(void *)(m->base + m->patch_off + 0x20);
        trap_stub[0] = 0x58000050u;
        trap_stub[1] = 0xD61F0200u;
        memcpy(&trap_stub[2], &(uintptr_t){(uintptr_t)kirby_trap_probe}, 8);
        uint32_t trap_off = 0x456c4u;
        int64_t trap_delta = (int64_t)(m->patch_off + 0x20) - (int64_t)trap_off;
        ((uint32_t *)(void *)(m->base + trap_off))[0] = 0x14000000u | ((uint32_t)((trap_delta >> 2) & 0x3ffffffu));
        fprintf(stderr, "[kirby] sdk abort trap hook installed at 0x456c4\n");
    }
}
