#!/usr/bin/env python3
"""Package an already built Kirby boot probe as a clearly named macOS preview."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def outside_repository(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError("preview App and build data must stay outside the source repository")
    return path


def clone(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-c", str(source.resolve()), str(target)], check=True)


def brew_dependencies(binary: Path) -> list[Path]:
    output = subprocess.check_output(["otool", "-L", str(binary)], text=True)
    result = []
    for line in output.splitlines()[1:]:
        name = line.strip().split(" (compatibility", 1)[0]
        if name.startswith("/opt/homebrew/"):
            result.append(Path(name))
    return result


def bundle_brew_libraries(binary: Path, contents: Path) -> None:
    """Keep the preview runnable without the build machine's Homebrew paths."""
    frameworks = contents / "Frameworks"
    sources: dict[str, Path] = {}
    queue = [binary]
    while queue:
        current = queue.pop()
        for dependency in brew_dependencies(current):
            real = dependency.resolve(strict=True)
            previous = sources.get(dependency.name)
            if previous and previous != real:
                raise ValueError(f"conflicting Homebrew libraries: {dependency.name}")
            if not previous:
                sources[dependency.name] = real
                queue.append(real)
    if not sources:
        return

    for name, source in sources.items():
        clone(source, frameworks / name)
        formula_root = source.parent.parent
        license_dir = contents / "Resources/licenses" / formula_root.parent.name
        for license_file in formula_root.iterdir():
            if license_file.is_file() and license_file.name.startswith(("LICENSE", "COPYING")):
                license_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(license_file, license_dir / license_file.name)

    for artifact, original in [(binary, binary), *[(frameworks / name, source) for name, source in sources.items()]]:
        for dependency in brew_dependencies(original):
            if artifact == binary:
                replacement = f"@loader_path/../../../Frameworks/{dependency.name}"
            else:
                replacement = f"@loader_path/{dependency.name}"
            subprocess.run(["install_name_tool", "-change", str(dependency), replacement, str(artifact)], check=True)
        if artifact != binary:
            subprocess.run(["install_name_tool", "-id", f"@loader_path/{artifact.name}", str(artifact)], check=True)
        subprocess.run(["codesign", "--force", "--sign", "-", str(artifact)], check=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True, help="external patched and built host root")
    parser.add_argument("--output", type=Path, required=True, help="new .app path outside the project")
    args = parser.parse_args()
    host = outside_repository(args.host)
    app = outside_repository(args.output)
    if app.suffix != ".app" or app.exists():
        raise ValueError("output must be a new .app path")
    if not (host / "analysis/phase12-validation.json").is_file():
        raise ValueError("host has no Kirby validation report")
    report = json.loads((host / "analysis/phase12-validation.json").read_text())
    if report.get("status") != "probe" or report.get("rom_version") != "v0":
        raise ValueError("host is not a validated base-version probe")

    game = app / "Contents/Resources/game"
    contents = app / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    files = [
        "build/totk-native",
        "rewritten/v0/main.patched.bin",
        "rewritten/v0/subsdk0.patched.bin",
        "rewritten/v0/sdk.patched.bin",
        "extracted/v0/romfs/romfs.bin",
        "extracted/v0/romfs/runtime-index.bin",
        "extracted/v0/romfs/index.json",
        "build/shader-service/totk_xlate",
        "build/spirv-cross/spirv-cross",
    ]
    for name in files:
        clone(host / name, game / name)
    fonts = host / "extracted/firmware/shared-fonts"
    manifest = json.loads((fonts / "manifest.json").read_text())
    if manifest.get("status") != "pass" or len(manifest.get("fonts", [])) != 6:
        raise ValueError("six verified shared fonts are required")
    for font in manifest["fonts"]:
        name = f"{font['type']}-{font['name']}.bfttf"
        clone(fonts / name, game / "extracted/firmware/shared-fonts" / name)
    bundle_brew_libraries(game / "build/totk-native", contents)

    (contents / "Info.plist").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Kirby Native Preview</string>
<key>CFBundleDisplayName</key><string>星之卡比 原生预览</string>
<key>CFBundleIdentifier</key><string>org.macnativegames.kirby.preview</string>
<key>CFBundleVersion</key><string>0.1</string>
<key>CFBundleShortVersionString</key><string>0.1</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleExecutable</key><string>KirbyPreview</string>
<key>LSMinimumSystemVersion</key><string>15.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
''')
    launcher = macos / "KirbyPreview"
    launcher.write_text('''#!/bin/zsh
set -eu
game="${0:A:h:h}/Resources/game"
data="$HOME/Library/Application Support/MacNativeGames/Kirby/preview"
mkdir -p "$data/profile" "$data/proof" "$data/slot" "$data/shader-cache"
export TOTK_ROMFS="$game/extracted/v0/romfs"
export TOTK_ROMFS_PATCHES=0
export TOTK_SHARED_FONTS="$game/extracted/firmware/shared-fonts"
export TOTK_PROFILE_DIR="$data/profile"
export TOTK_ROMFS_PROOF_DIR="$data/proof"
export TOTK_GAME_SLOT_DIR="$data/slot"
export TOTK_SHADER_CACHE="$data/shader-cache"
export TOTK_SHADER_SEED=off
export TOTK_GPU_ALLOW_SUBMIT=1
export KIRBY_PREVIEW=1
export KIRBY_VERTEX_Y_FLIP=1
export TOTK_GPU_WINDING_FLIP=1
export KIRBY_PRESENT_FLIP_Y=1
export TOTK_FPS_OVERLAY=1
export TOTK_SHADER_OVERLAY=1
export TOTK_LOAD_OVERLAY=1
export TOTK_SLOT_OWNER=kirby-preview
export TOTK_SLOT_PURPOSE='Kirby native preview'
cd "$game"
exec "$game/build/totk-native" "$game/rewritten/v0" boot >> "$data/latest.log" 2>&1
''')
    launcher.chmod(0o755)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    print(app)


if __name__ == "__main__":
    main()
