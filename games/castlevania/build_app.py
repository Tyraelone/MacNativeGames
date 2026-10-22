#!/usr/bin/env python3
"""Assemble the verified Castlevania 1.1.0 native main game outside this source tree."""
import argparse
import json
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
from packaging_common import clone_file as clone, outside_repository, sha256_file as digest, verified_file
ROMFS_SHA256 = "2ba74cc0e68efc9202880b6ea92d2e9cc5193069a7bbc17e85d1ffb68fa77247"
DLC_SHA256 = "853d89ef4aad9f627401c79d2cb12c6533dced4247f3f2202f94f4c6a7a2ba05"
TITLE_IDS = ("0100BA4026E95001", "0100BA4026E95002")


def checked(path, expected=None):
    try:
        return verified_file(path, expected)
    except ValueError as error:
        raise SystemExit(str(error)) from None


def build_icon(source: Path, destination: Path, work: Path) -> None:
    """Build the macOS icon from the tracked square artwork outside the source tree."""
    checked(source)
    with tempfile.TemporaryDirectory(prefix="castlevania-icon-", dir=work) as temporary:
        iconset = Path(temporary) / "AppIcon.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(["sips", "-s", "format", "png", "-z", str(size * scale),
                                str(size * scale), str(source), "--out", str(iconset / name)],
                               check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["iconutil", "-c", "icns", "-o", str(destination), str(iconset)], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, required=True, help="external verified Castlevania_build directory")
    p.add_argument("--out", type=Path, required=True, help="external .app path")
    p.add_argument("--shader-seed", type=Path, help="external prepared gameplay shader seed")
    args = p.parse_args()
    try:
        work, out = outside_repository(args.work, REPO), outside_repository(args.out, REPO)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    if out.suffix != ".app":
        raise SystemExit("App output must end in .app")
    if out.exists():
        raise SystemExit(f"Output already exists; preserving it: {out}")
    source = work / "main/update"
    host = work / "native-host"
    native = host / "build/totk-native"
    romfs = source / "romfs"
    index = json.loads((romfs / "index.json").read_text())
    if index.get("status") != "pass" or index.get("romfs_sha256") != ROMFS_SHA256 or index.get("romfs_size") != 3600101664:
        raise SystemExit("The verified 1.1.0 RomFS index does not match this game")
    files = {
        "build/totk-native": native,
        "build/shader-service/totk_xlate": REPO / "games/totk/prebuilt/macos-arm64/totk_xlate",
        "build/spirv-cross/spirv-cross": host / "build/spirv-cross/spirv-cross",
        "rewritten/main.patched.bin": source / "rewritten-indirect/main.patched.bin",
        "rewritten/sdk.patched.bin": source / "rewritten/sdk.patched.bin",
        "rewritten/subsdk0.patched.bin": source / "rewritten/subsdk0.patched.bin",
        "main/romfs/romfs.bin": romfs / "romfs.bin",
        "main/romfs/runtime-index.bin": romfs / "runtime-index.bin",
        "main/romfs/index.json": romfs / "index.json",
    }
    for title in TITLE_IDS:
        folder = work / "main/addons-verified" / title
        files[f"addons/{title}/romfs.bin"] = folder / "romfs.bin"
        files[f"addons/{title}/index.json"] = folder / "index.json"
    seed_count = 0
    if args.shader_seed:
        if args.shader_seed.is_symlink():
            raise SystemExit("Shader seed must be a regular directory outside the source project")
        try:
            seed = outside_repository(args.shader_seed, REPO)
        except ValueError as error:
            raise SystemExit(str(error)) from None
        if not seed.is_dir():
            raise SystemExit("Shader seed must be a regular directory outside the source project")
        seed_manifest = json.loads((seed / "seed-manifest.json").read_text())
        if (seed_manifest.get("schema") != 1 or seed_manifest.get("chain") != "totk-native-v4-unverified"
                or seed_manifest.get("source_romfs_sha256") != ROMFS_SHA256
                or not isinstance(seed_manifest.get("files"), dict) or seed_manifest.get("shaders", 0) < 1):
            raise SystemExit("Shader seed identity does not match this main game")
        for name, expected in seed_manifest["files"].items():
            if name in ("", ".", "..") or Path(name).name != name:
                raise SystemExit(f"Unsafe shader seed filename: {name}")
            source_file = seed / name
            checked(source_file, expected)
            files[f"build/shader-seed/{name}"] = source_file
        files["build/shader-seed/seed-manifest.json"] = seed / "seed-manifest.json"
        seed_count = seed_manifest["shaders"]
    hashes = {}
    for rel, path in files.items():
        expected = ROMFS_SHA256 if rel == "main/romfs/romfs.bin" else DLC_SHA256 if rel.endswith("/romfs.bin") and rel.startswith("addons/") else None
        hashes[rel] = checked(path, expected)
    tmp = out.with_name(out.name + f".staging-{os.getpid()}")
    if tmp.exists():
        raise SystemExit(f"Staging path already exists: {tmp}")
    resources = tmp / "Contents/Resources/castlevania"
    for rel, path in files.items():
        clone(path, resources / rel)
    build_icon(REPO / "games/castlevania/assets/app-icon.png", tmp / "Contents/Resources/AppIcon.icns", work)
    for title in TITLE_IDS:
        index = json.loads((work / "main/addons-verified" / title / "index.json").read_text())
        if index.get("status") != "pass" or index.get("romfs_sha256") != DLC_SHA256 or index.get("files") != [{"path": "VENOM", "offset": 512, "size": 322}]:
            raise SystemExit(f"Unverified add-on file layout: {title}")
        image = work / "main/addons-verified" / title / "romfs.bin"
        with image.open("rb") as f:
            f.seek(512)
            content = f.read(322)
        if len(content) != 322:
            raise SystemExit(f"Truncated add-on file: {title}")
        rel = f"addons/{title}/files/VENOM"
        target = resources / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        hashes[rel] = digest(target)
    manifest = {
        "format": 1, "title_id": "0100BA4026E94000", "main_version": "1.1.0",
        "main_romfs_sha256": ROMFS_SHA256, "files_sha256": hashes,
        "addon_title_ids": list(TITLE_IDS),
        "addon_runtime_status": "native AOC enumeration and read-only mount; game use not yet verified",
        "gallery_status": "omitted at user request",
        "bundled_gameplay_shaders": seed_count,
    }
    (resources / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    launcher = tmp / "Contents/MacOS/Castlevania"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["xcrun", "clang", "-fobjc-arc", "-O2", "-Wall",
                    str(REPO / "games/castlevania/launcher.m"), "-framework", "AppKit", "-o", str(launcher)], check=True)
    info = {
        "CFBundleDevelopmentRegion": "zh_CN", "CFBundleExecutable": "Castlevania",
        "CFBundleIdentifier": "org.macnativegames.castlevania.belmonts-curse",
        "CFBundleName": "Castlevania Belmont's Curse", "CFBundleDisplayName": "恶魔城：贝尔蒙特的诅咒",
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion": "1", "LSMinimumSystemVersion": "26.0",
        "NSHighResolutionCapable": True, "LSApplicationCategoryType": "public.app-category.action-games",
        "LSSupportsGameMode": True, "GCSupportsControllerUserInteraction": True,
    }
    (tmp / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    (tmp / "Contents/PkgInfo").write_bytes(b"APPL????")
    subprocess.run(["codesign", "--force", "--sign", "-", str(tmp)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(tmp)], check=True)
    subprocess.run([str(launcher), "--check"], check=True)
    tmp.rename(out)
    print(out)


if __name__ == "__main__":
    main()
