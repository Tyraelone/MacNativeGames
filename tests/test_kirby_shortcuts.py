"""Compile the shipped Kirby adaptation without requiring personal game files."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
KIRBY_HOST_BASE = 'f5cc1519c5c6aed8b21c20317a9cee15f3f6d746'


def pinned_game_patches(destination):
    source = subprocess.check_output(
        ['git', 'show', f'{KIRBY_HOST_BASE}:games/totk/runtime/game_patches.c'], cwd=ROOT)
    destination.write_bytes(source)


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('clang'), 'macOS native runtime')
class KirbyShortcutsTests(unittest.TestCase):
    def test_picture_cycle_publishes_size_and_resets_upscaler(self):
        with tempfile.TemporaryDirectory(prefix='kirby-shortcuts-') as tmp:
            work = Path(tmp)
            (work / 'runtime').mkdir()
            pinned_game_patches(work / 'runtime/game_patches.c')
            for name in ('game_patches.h', 'runtime.h'):
                shutil.copy2(ROOT / 'games/totk/runtime' / name, work / 'runtime' / name)
            subprocess.run(['git', 'apply', '--include=runtime/game_patches.c',
                            str(ROOT / 'games/kirby/native-preview.patch')], cwd=work, check=True)
            (work / 'case.c').write_text(r'''
#include "runtime/game_patches.c"
#include <assert.h>
#include <stdlib.h>
static int upscale, output;
void dm_gfx_set_flag(const char *name,int value) {
    if(!strcmp(name,"mfx_upscale"))upscale=value;
    else if(!strcmp(name,"mfx_output"))output=value;
    else abort();
}
_Noreturn void runtime_fail(const char *message){(void)message;abort();}
int main(void) {
    _Atomic uint64_t size=pack(1920,1080),limits[2];output_size=&size;dynamic_limits=limits;
    for(int i=0;i<5;i++) {
        assert(runtime_output_mode_cycle()==1);runtime_frame_step_update(1);
        assert(atomic_load(limits)==pack(1920,1080)&&atomic_load(limits+1)==pack(1440,810));
        assert(upscale==1&&output==1&&atomic_load(&size)==pack(1920,1080));
        assert(runtime_output_mode_cycle()==2);runtime_frame_step_update(2);
        assert(atomic_load(limits)==pack(2560,1440)&&atomic_load(limits+1)==pack(2560,1440));
        assert(upscale==0&&output==0&&atomic_load(&size)==pack(2560,1440));
        assert(runtime_output_mode_cycle()==0);runtime_frame_step_update(3);
        assert(atomic_load(limits)==pack(1920,1080)&&atomic_load(limits+1)==pack(1440,810));
        assert(upscale==0&&output==0&&atomic_load(&size)==pack(1920,1080));
    }
}
''')
            subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(work / 'case.c'), '-o', str(work / 'case')], check=True)
            subprocess.run([str(work / 'case')], check=True, capture_output=True)

    def test_hidden_hints_first_press_reveals_enabled_overlays(self):
        with tempfile.TemporaryDirectory(prefix='kirby-hints-') as tmp:
            work = Path(tmp)
            rel = Path('third_party/d2r_gfx/gfx/nvn/fps_overlay.c')
            (work / rel.parent).mkdir(parents=True)
            shutil.copy2(ROOT / 'games/totk' / rel, work / rel)
            subprocess.run(['git', 'apply', '--include=' + str(rel),
                            str(ROOT / 'games/kirby/native-preview.patch')], cwd=work, check=True)
            (work / 'case.c').write_text(r'''
#include "fps_overlay.h"
#include <assert.h>
int main(void) {
    assert(!fps_overlay_hints_enabled());
    assert(fps_overlay_enabled());
    assert(fps_overlay_toggle_hints());
    assert(fps_overlay_hints_enabled());
    assert(!fps_overlay_toggle_hints());
    assert(!fps_overlay_hints_enabled());
}
''')
            source = ROOT / 'games/totk' / rel.parent
            subprocess.run(['clang', '-std=c11', '-I', str(source),
                            str(work / 'case.c'), str(work / rel),
                            '-framework', 'CoreGraphics', '-framework', 'CoreText',
                            '-framework', 'CoreFoundation', '-o', str(work / 'case')], check=True)
            env = {**os.environ, 'KIRBY_PREVIEW': '1', 'TOTK_FPS_OVERLAY': '1'}
            subprocess.run([str(work / 'case')], env=env, check=True)

    def test_frame_pacing_patch_preserves_other_rates_and_checks_originals(self):
        with tempfile.TemporaryDirectory(prefix='kirby-pacer-') as tmp:
            work = Path(tmp)
            (work / 'runtime').mkdir()
            pinned_game_patches(work / 'runtime/game_patches.c')
            for name in ('game_patches.h', 'runtime.h'):
                shutil.copy2(ROOT / 'games/totk/runtime' / name, work / 'runtime' / name)
            subprocess.run(['git', 'apply', '--include=runtime/game_patches.c',
                            str(ROOT / 'games/kirby/native-preview.patch')], cwd=work, check=True)
            (work / 'case.c').write_text(r'''
#include "runtime/game_patches.c"
#include <assert.h>
#include <stdlib.h>
void dm_gfx_set_flag(const char *name,int value){(void)name;(void)value;}
_Noreturn void runtime_fail(const char *message){(void)message;exit(73);}
int main(int argc,char **argv) {
    (void)argv;
    uint32_t ticks[]={1,2,3,4,5,6};
    if(argc>1)ticks[1]=7;
    frame_pacing_patch(ticks);
    assert(ticks[0]==1&&ticks[1]==1&&ticks[2]==3&&ticks[3]==4&&ticks[4]==5&&ticks[5]==6);
}
''')
            subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(work / 'case.c'), '-o', str(work / 'case')], check=True)
            subprocess.run([str(work / 'case')], check=True)
            self.assertEqual(subprocess.run([str(work / 'case'), 'bad-build']).returncode, 73)
