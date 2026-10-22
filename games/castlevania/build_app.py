#!/usr/bin/env python3
"""Assemble the verified Castlevania 1.1.0 native main game outside this source tree."""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROMFS_SHA256 = "2ba74cc0e68efc9202880b6ea92d2e9cc5193069a7bbc17e85d1ffb68fa77247"
DLC_SHA256 = "853d89ef4aad9f627401c79d2cb12c6533dced4247f3f2202f94f4c6a7a2ba05"
TITLE_IDS = ("0100BA4026E95001", "0100BA4026E95002")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def checked(path, expected=None):
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"Missing regular input: {path}")
    actual = digest(path)
    if expected and actual != expected:
        raise SystemExit(f"SHA-256 mismatch: {path}: {actual}")
    return actual


def clone(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["cp", "-c", str(source), str(target)], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        shutil.copy2(source, target)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, required=True, help="external verified Castlevania_build directory")
    p.add_argument("--out", type=Path, required=True, help="external .app path")
    p.add_argument("--shader-seed", type=Path, help="external prepared gameplay shader seed")
    args = p.parse_args()
    work, out = args.work.expanduser().resolve(), args.out.expanduser().absolute()
    if out.suffix != ".app" or out.is_relative_to(REPO) or work.is_relative_to(REPO):
        raise SystemExit("Work and .app output must be outside the source project")
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
        seed = args.shader_seed.expanduser().resolve()
        if seed.is_relative_to(REPO) or not seed.is_dir() or seed.is_symlink():
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
