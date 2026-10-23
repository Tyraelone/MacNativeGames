#ifndef MNG_NVN_PROGRAM_BIND_H
#define MNG_NVN_PROGRAM_BIND_H

/* The current host resolves vertex + fragment as one graphics program and
   compute as another. Unselected sides keep their previous program. Partial
   graphics binds still need a real per-stage program composition. */
static inline int nvn_bind_keeps_graphics(int stages, int enabled) {
    return enabled && !(stages & 0x3);
}

static inline int nvn_bind_keeps_compute(int stages, int enabled) {
    return enabled && !(stages & 0x20);
}

#endif
