"""Exercise the actual source loader used by derived Metal vertex functions."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('clang'), 'macOS shader host')
class KirbyShaderSourceTests(unittest.TestCase):
    def test_derived_vertices_keep_orientation_with_and_without_source_cache(self):
        with tempfile.TemporaryDirectory(prefix='kirby-source-') as tmp:
            work = Path(tmp)
            rel = Path('third_party/d2r_gfx/gfx/nvn/nvn_mtl.m')
            (work / rel.parent).mkdir(parents=True)
            shutil.copy2(ROOT / 'games/totk' / rel, work / rel)
            subprocess.run(['git', 'apply', '--include=' + str(rel),
                            str(ROOT / 'games/kirby/native-preview.patch')], cwd=work, check=True)
            source = (work / rel).read_text()
            start = source.find('static NSString *kirby_shader_source(')
            if start < 0:
                start = source.index('static NSString *sh_src(')
            actual = source[start:source.index('static int sh_has_src(', start)]
            case = r'''
#import <Foundation/Foundation.h>
#include <stdlib.h>
@interface NvShader : NSObject { @public int stage; NSString *src, *src_path; } @end
@implementation NvShader @end
@ACTUAL@
int main(void) { @autoreleasepool {
    NSString *original=@"vertex main0_out main0() {\n    main0_out out = {};\n    out.gl_Position.x = 0.0;\n    return out;\n}\n";
    NSString *path=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    [original writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:nil];
    NvShader *s=[NvShader new]; s->stage=0; s->src_path=path;
    NSString *disk=sh_src(s);
    s->src=original; NSString *cached=sh_src(s);
    if(![disk containsString:@"out.gl_Position.y = -out.gl_Position.y;"] || ![disk isEqual:cached])return 1;
    s->src=cached;
    if(![sh_src(s) isEqual:cached])return 2;
    s->stage=1; s->src=original;
    if(![sh_src(s) isEqual:original])return 3;
    s->stage=0; unsetenv("KIRBY_VERTEX_Y_FLIP");
    if(![sh_src(s) isEqual:original])return 4;
    [[NSFileManager defaultManager] removeItemAtPath:path error:nil];
} }
'''.replace('@ACTUAL@', actual)
            (work / 'case.m').write_text(case)
            subprocess.run(['clang', '-fobjc-arc', '-Wno-incompatible-pointer-types',
                            str(work / 'case.m'), '-framework', 'Foundation', '-o', str(work / 'case')], check=True)
            subprocess.run([str(work / 'case')], env={**os.environ, 'KIRBY_VERTEX_Y_FLIP': '1'}, check=True)

    def test_keepalive_policy_preserves_heavy_modes_and_explicit_override(self):
        with tempfile.TemporaryDirectory(prefix='kirby-keepalive-') as tmp:
            work = Path(tmp)
            rel = Path('third_party/d2r_gfx/gfx/nvn/nvn_mtl.m')
            (work / rel.parent).mkdir(parents=True)
            shutil.copy2(ROOT / 'games/totk' / rel, work / rel)
            subprocess.run(['git', 'apply', '--include=' + str(rel),
                            str(ROOT / 'games/kirby/native-preview.patch')], cwd=work, check=True)
            source = (work / rel).read_text()
            start = source.index('static int keepalive_needed(')
            actual = source[start:source.index('static void keepalive_start(', start)]
            (work / 'case.c').write_text(actual + r'''
#include <assert.h>
int main(void) {
    assert(!keepalive_needed(1,0,0));
    for(int mode=1;mode<=3;mode++)assert(keepalive_needed(1,mode,0));
    assert(keepalive_needed(1,0,1));
    assert(keepalive_needed(0,0,0));
}
''')
            subprocess.run(['clang', str(work / 'case.c'), '-o', str(work / 'case')], check=True)
            subprocess.run([str(work / 'case')], check=True)
