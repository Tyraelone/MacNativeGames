#ifndef MNG_NVN_PROGRAM_BIND_H
#define MNG_NVN_PROGRAM_BIND_H

/* A null bind that selects no vertex or fragment stage cannot clear the
   current graphics program. This is the verified Castlevania mask pattern;
   full independent stage binding requires a separate state representation. */
static inline int nvn_bind_keeps_graphics(const void *program, int stages, int enabled) {
    return enabled && !program && !(stages & 0x3);
}

#endif
