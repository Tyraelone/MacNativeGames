import subprocess
import tempfile
import unittest
from pathlib import Path


NVN_DIR = Path(__file__).resolve().parents[1] / "games/totk/third_party/d2r_gfx/gfx/nvn"


class ProgramBindTests(unittest.TestCase):
    def test_non_graphics_null_bind_preserves_graphics_only_when_enabled(self):
        source = r'''
#include <assert.h>
#include "nvn_program_bind.h"

int main(void) {
    int graphics = 1, replacement = 2;
    const void *current = &graphics;
    const void *next = &replacement;

    assert(!nvn_bind_keeps_graphics(next, 0x3, 1));
    current = next;
    assert(nvn_bind_keeps_graphics(0, 0x3c, 1));
    assert(current == next);
    assert(nvn_bind_keeps_graphics(0, 0x20, 1));
    assert(!nvn_bind_keeps_graphics(0, 0x3c, 0));
    assert(!nvn_bind_keeps_graphics(0, 0x1, 1));
    assert(!nvn_bind_keeps_graphics(0, 0x2, 1));
    assert(!nvn_bind_keeps_graphics(0, 0x3, 1));
    assert(nvn_bind_keeps_graphics(0, 0, 1));
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
