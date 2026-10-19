/* Kirby Star Allies experimental profile: no game-code patches yet.
   The SDK 4.4 game is started unmodified; output-size and frame-step probes
   are kept as no-ops so the shared runtime can link. */
#include "game_patches.h"
#include "game_version.h"
#include <stdio.h>
#include <string.h>

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
}
