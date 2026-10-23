#!/usr/bin/env python3
"""Package the verified Mario Wonder native host outside the source tree."""

import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
HOST = REPO / "games" / "totk"
SYNC = (
    "Makefile", "runtime/loader.c", "runtime/services.c", "runtime/account.c", "runtime/time_host.c",
    "runtime/ipc.c", "runtime/fs_host.c", "runtime/frontend.m", "runtime/game_version.h",
    "third_party/d2r_gfx/gfx/nvn/nvn_refl.h",
    "third_party/d2r_gfx/gfx/nvn/nvn_refl.m",
    "third_party/d2r_gfx/gfx/nvn/nvn_mtl.m",
)
MARIO_VARIANT_MARKER = b"MNG_MARIO_WONDER_1_2_1"


def external(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError(f"generated files must be outside the source tree: {path}")
    return path


def require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def verify_native_variant(path: Path) -> None:
    if MARIO_VARIANT_MARKER not in require(path).read_bytes():
        raise ValueError(f"native binary is not the Mario Wonder 1.2.1 variant: {path}")


def build_icon(image: Path, resources: Path, scratch: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="mario-icon-", dir=scratch) as temp:
        iconset = Path(temp) / "MarioWonder.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                pixels = size * scale
                if pixels > 512:
                    continue
                name = f"icon_{size}x{size}" + ("@2x" if scale == 2 else "") + ".png"
                subprocess.run(["sips", "-s", "format", "png", "-z", str(pixels), str(pixels),
                                str(image), "--out", str(iconset / name)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(resources / "MarioWonder.icns")], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path, help="external MarioWonder_build directory")
    parser.add_argument("--output", required=True, type=Path, help="new external .app path")
    args = parser.parse_args()
    work, output = external(args.work), external(args.output)
    if output.suffix != ".app" or output.exists():
        parser.error("--output must be a new .app path")
    host = require(external(work / "native-host"))
    version = require(work / "update/control.nacp").read_bytes()[0x3060:0x3070].split(b"\0", 1)[0]
    if version != b"1.2.1":
        raise ValueError(f"expected verified update 1.2.1, got {version!r}")
    required = (
        work / "update/romfs", work / "update/packed-rewrites/main.patched.bin",
        work / "update/packed-rewrites/sdk.patched.bin",
        host / "build/shader-service/totk_xlate", host / "build/spirv-cross/spirv-cross",
        host / "extracted/firmware/shared-fonts", host / "build/local-avatar.jpg",
    )
    for path in required: require(path)
    for rel in SYNC:
        source, target = HOST / rel, host / rel
        if source.read_bytes() != target.read_bytes():
            shutil.copyfile(source, target)
    env = os.environ.copy()
    env.setdefault("SDKROOT", "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk")
    subprocess.run(["make", "-j4", "NATIVE_OPT=-O1 -DMARIO_NATIVE_PROBE=1",
                    "NATIVE_BINARY=build/mario-wonder-native", "GFX_BUILD_ROOT=build/gfx-mario",
                    "build/mario-wonder-native"],
                   cwd=host, env=env, check=True)
    verify_native_variant(host / "build/mario-wonder-native")
    output.parent.mkdir(parents=True, exist_ok=True)
    app = output.with_name(output.name + f".incomplete-{os.getpid()}")
    if app.exists():
        raise FileExistsError(app)
    macos = app / "Contents/MacOS"
    resources = app / "Contents/Resources"
    game = resources / "game"
    macos.mkdir(parents=True)
    (game / "build/shader-service").mkdir(parents=True)
    (game / "build/spirv-cross").mkdir(parents=True)
    (game / "rewritten").mkdir()
    (game / "extracted/firmware").mkdir(parents=True)
    shutil.copy2(host / "build/mario-wonder-native", game / "build/mario-wonder-native")
    shutil.copy2(host / "build/shader-service/totk_xlate", game / "build/shader-service/totk_xlate")
    shutil.copy2(host / "build/spirv-cross/spirv-cross", game / "build/spirv-cross/spirv-cross")
    shutil.copy2(host / "build/local-avatar.jpg", game / "build/local-avatar.jpg")
    for name in ("main", "sdk"):
        shutil.copy2(work / f"update/packed-rewrites/{name}.patched.bin",
                     game / f"rewritten/{name}.patched.bin")
    subprocess.run(["cp", "-cR", str(work / "update/romfs"), str(game / "romfs")], check=True)
    subprocess.run(["cp", "-cR", str(host / "extracted/firmware/shared-fonts"),
                    str(game / "extracted/firmware/shared-fonts")], check=True)
    subprocess.run(["xcrun", "clang", "-fobjc-arc", str(Path(__file__).with_name("launcher.m")),
                    "-framework", "AppKit", "-o", str(macos / "MarioWonder")], check=True, env=env)
    build_icon(host / "build/local-avatar.jpg", resources, work)
    info = {
        "CFBundleDevelopmentRegion": "zh_CN", "CFBundleExecutable": "MarioWonder",
        "CFBundleIdentifier": "local.macnativegames.mario-wonder.preview",
        "CFBundleIconFile": "MarioWonder.icns", "CFBundleName": "超级马里奥兄弟 惊奇",
        "CFBundleDisplayName": "超级马里奥兄弟 惊奇",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.2.1",
        "CFBundleVersion": "1", "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
    }
    with (app / "Contents/Info.plist").open("wb") as file:
        plistlib.dump(info, file)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    app.rename(output)
    print(output)


if __name__ == "__main__":
    main()
