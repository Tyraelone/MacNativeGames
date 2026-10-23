import subprocess
import tempfile
import unittest
from pathlib import Path


NVN_DIR = Path(__file__).resolve().parents[1] / "games/totk/third_party/d2r_gfx/gfx/nvn"


class ProgramBindTests(unittest.TestCase):
    def test_graphics_and_compute_masks_keep_unselected_program(self):
        source = r'''
#include <assert.h>
#include "nvn_program_bind.h"

int main(void) {
    int graphics = 1, replacement = 2;
    const void *current = &graphics;
    const void *next = &replacement;

    assert(!nvn_bind_keeps_graphics(0x3, 1));
    current = next;
    assert(nvn_bind_keeps_graphics(0x3c, 1));
    assert(current == next);
    assert(nvn_bind_keeps_graphics(0x20, 1));
    assert(nvn_bind_keeps_compute(0x3, 1));
    assert(!nvn_bind_keeps_compute(0x20, 1));
    assert(!nvn_bind_keeps_compute(0x3c, 1));
    assert(!nvn_bind_keeps_compute(0x3, 0));
    assert(!nvn_bind_keeps_graphics(0x3c, 0));
    assert(!nvn_bind_keeps_graphics(0x1, 1));
    assert(!nvn_bind_keeps_graphics(0x2, 1));
    assert(!nvn_bind_keeps_graphics(0x3, 1));
    assert(nvn_bind_keeps_graphics(0, 1));

    const void *graphics_program = 0, *compute_program = 0;
    if (!nvn_bind_keeps_graphics(0x3, 1)) graphics_program = &graphics;
    if (!nvn_bind_keeps_compute(0x3, 1)) compute_program = &graphics;
    assert(graphics_program == &graphics && compute_program == 0);
    if (!nvn_bind_keeps_graphics(0x20, 1)) graphics_program = &replacement;
    if (!nvn_bind_keeps_compute(0x20, 1)) compute_program = &replacement;
    assert(graphics_program == &graphics && compute_program == &replacement);
    if (!nvn_bind_keeps_graphics(0x3c, 1)) graphics_program = 0;
    if (!nvn_bind_keeps_compute(0x3c, 1)) compute_program = 0;
    assert(graphics_program == &graphics && compute_program == 0);

    if (!nvn_bind_keeps_graphics(0x3c, 0)) graphics_program = 0;
    if (!nvn_bind_keeps_compute(0x3c, 0)) compute_program = 0;
    assert(graphics_program == 0 && compute_program == 0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="mng-nvn-bind-") as folder:
            work = Path(folder)
            (work / "probe.c").write_text(source)
            subprocess.run(
                ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(NVN_DIR),
                 str(work / "probe.c"), "-o", str(work / "probe")],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(work / "probe")], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
