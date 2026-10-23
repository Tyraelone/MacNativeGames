#!/usr/bin/env python3
"""Package the verified Mario Wonder native host outside the source tree."""

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
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
    "third_party/d2r_gfx/gfx/nvn/nvn_obj.h",
    "third_party/d2r_gfx/gfx/nvn/hle_nvn.c",
    "third_party/d2r_gfx/gfx/nvn/totk_shader_rt.h",
    "third_party/d2r_gfx/gfx/nvn/totk_shader_rt.m",
    "third_party/d2r_gfx/gfx/nvn/nvn_mtl.m",
)
MARIO_VARIANT_MARKER = b"MNG_MARIO_WONDER_1_2_1"
SHADER_CHAIN = "totk-native-v4-unverified"
VARIANT_NAME = re.compile(r"[0-9a-f]{64}-[0-9a-f]{12}")
SHADER_KEY = re.compile(r"[0-9a-f]{64}-[0-9a-f]{12}_b")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def recorded_cache_identity(cache: Path) -> str:
    """Include every packaged shader input so a changed cache cannot reuse a stale seed."""
    collected = require(cache / "pso_collected.tsv")
    inputs = [collected]
    for path in cache.iterdir():
        if (re.fullmatch(r"[0-9a-f]{64}\.variants", path.name) or
                re.fullmatch(r"[0-9a-f]{64}-[0-9a-f]{12}_b\.(?:metal|json)", path.name)) and path.is_file():
            inputs.append(path)
    identity = hashlib.sha256()
    for path in sorted(inputs, key=lambda item: item.name):
        identity.update(path.name.encode() + b"\0")
        identity.update(bytes.fromhex(digest(path.read_bytes())))
    return identity.hexdigest()[:16]


def prepare_recorded_seed(cache: Path, output: Path) -> dict:
    """Export only complete, chain-matched graphics variants from a played cache."""
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mario-seed-", dir=output.parent) as tmp:
        staging = Path(tmp)
        valid = {}
        indexes = 0
        for index in sorted(cache.glob("*.variants")):
            if not re.fullmatch(r"[0-9a-f]{64}\.variants", index.name):
                continue
            try:
                rows = json.loads(index.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(rows, list):
                continue
            clean = []
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("deps"), dict):
                    continue
                variant = row.get("variant")
                if not isinstance(variant, str) or not VARIANT_NAME.fullmatch(variant) or not variant.startswith(index.stem + "-"):
                    continue
                metal, reflection = cache / f"{variant}_b.metal", cache / f"{variant}_b.json"
                if not metal.is_file() or not reflection.is_file():
                    continue
                try:
                    meta = json.loads(reflection.read_text())
                except (OSError, ValueError):
                    continue
                if (meta.get("chain") != SHADER_CHAIN or meta.get("stage") not in ("vs", "ps", "cs") or
                        meta.get("deps") != row["deps"] or not isinstance(meta.get("entry"), str)):
                    continue
                if not metal.stat().st_size or metal.stat().st_size > 2_000_000:
                    continue
                shutil.copy2(metal, staging / metal.name)
                shutil.copy2(reflection, staging / reflection.name)
                valid[f"{variant}_b"] = meta["stage"]
                clean.append(row)
            if clean:
                (staging / index.name).write_text(json.dumps(clean, separators=(",", ":")) + "\n")
                indexes += 1
        if not valid:
            raise ValueError("recorded cache has no complete shaders for this translation chain")
        collected = cache / "pso_collected.tsv"
        lines = []
        if collected.is_file():
            for line in collected.read_text().splitlines():
                parts = line.split("\t")
                if len(parts) == 3 and parts[0] == "S" and SHADER_KEY.fullmatch(parts[1]) and valid.get(parts[1]) == {"0": "vs", "1": "ps", "5": "cs"}.get(parts[2]):
                    lines.append(line)
                elif len(parts) == 2 and parts[0] == "C" and valid.get(parts[1]) == "cs":
                    lines.append(line)
                elif len(parts) == 2 and parts[0] == "R" and len(parts[1]) <= 4096 and re.fullmatch(r"[0-9a-f]+", parts[1]):
                    lines.append(line)
        (staging / "pso_manifest.tsv").write_text("\n".join(dict.fromkeys(lines)) + "\n")
        files = {p.name: digest(p.read_bytes()) for p in sorted(staging.iterdir()) if p.is_file()}
        report = {"schema": 1, "chain": SHADER_CHAIN, "shaders": len(valid), "indexes": indexes,
                  "pipeline_rows": sum(line.startswith(("R\t", "C\t")) for line in lines), "files": files}
        (staging / "seed-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        staging.rename(output)
        return report


def merge_shader_seeds(seeds: list[Path], output: Path) -> dict:
    """Combine exact recorded variants with extracted defaults, preserving index order."""
    if not seeds or output.exists():
        raise ValueError("at least one input seed and a new output path are required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mario-merged-seed-", dir=output.parent) as tmp:
        staging = Path(tmp)
        indexes = {}
        rows = []
        seen_rows = set()
        for seed in seeds:
            report = verify_recorded_seed(seed)
            for name in report["files"]:
                source = seed / name
                if name.endswith(".variants"):
                    bucket = indexes.setdefault(name, [])
                    present = {item["variant"] for item in bucket}
                    for item in json.loads(source.read_text()):
                        if item["variant"] not in present:
                            bucket.append(item)
                            present.add(item["variant"])
                elif name == "pso_manifest.tsv":
                    for line in source.read_text().splitlines():
                        if line and not line.startswith("#") and line not in seen_rows:
                            rows.append(line)
                            seen_rows.add(line)
                else:
                    target = staging / name
                    if target.exists():
                        if digest(target.read_bytes()) != report["files"][name]:
                            raise ValueError(f"conflicting shader seed file: {name}")
                    else:
                        shutil.copy2(source, target)
        for name, variants in indexes.items():
            (staging / name).write_text(json.dumps(variants, separators=(",", ":")) + "\n")
        (staging / "pso_manifest.tsv").write_text("\n".join(rows) + "\n")
        report = {"schema": 1, "chain": SHADER_CHAIN,
                  "shaders": len(list(staging.glob("*_b.metal"))), "indexes": len(indexes),
                  "pipeline_rows": sum(line.startswith(("R\t", "C\t")) for line in rows),
                  "files": {p.name: digest(p.read_bytes()) for p in sorted(staging.iterdir())}}
        (staging / "seed-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        staging.rename(output)
        return report


def compile_recorded_libraries(seed: Path, libs: Path, jobs: int = 4) -> tuple[int, int]:
    """Compile exact MSL sources using the renderer's safe-math setting."""
    compiler = subprocess.run(["xcrun", "-f", "metal"], check=True, capture_output=True, text=True).stdout.strip()
    libs.mkdir(parents=True, exist_ok=True)
    todo = {}
    for source in sorted(seed.glob("*_b.metal")):
        todo.setdefault(digest(source.read_bytes()), source)

    def compile_one(item: tuple[str, Path]) -> str | None:
        key, source = item
        target = libs / f"{key}.metallib"
        if target.is_file() and target.read_bytes().startswith(b"MTLB"):
            return None
        partial = libs / f"{key}.partial"
        result = subprocess.run([compiler, "-fmetal-math-mode=safe", "-o", str(partial), str(source)],
                                capture_output=True, text=True)
        if result.returncode or not partial.is_file() or not partial.read_bytes().startswith(b"MTLB"):
            partial.unlink(missing_ok=True)
            return f"{source.name}: {result.stderr.strip() or result.stdout.strip() or 'invalid library'}"
        partial.replace(target)
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(compile_one, todo.items()))
    failures = [message for message in results if message]
    (libs / "failures.txt").write_text("\n".join(failures) + ("\n" if failures else ""))
    return len(todo) - len(failures), len(failures)


def verify_recorded_seed(seed: Path) -> dict:
    try:
        report = json.loads((seed / "seed-manifest.json").read_text())
        if (report.get("schema") != 1 or report.get("chain") != SHADER_CHAIN or
                not isinstance(report.get("shaders"), int) or report["shaders"] < 1 or
                not isinstance(report.get("files"), dict) or not report["files"]):
            raise ValueError("shader seed identity is invalid")
        listed = set(report["files"]) | {"seed-manifest.json"}
        for path in seed.iterdir():
            if path.name not in listed or not path.is_file() or path.is_symlink():
                raise ValueError(f"unlisted or unsafe shader seed file: {path.name}")
        for name, expected in report["files"].items():
            if (Path(name).name != name or not re.fullmatch(
                    r"(?:[0-9a-f]{64}\.variants|[0-9a-f]{64}-[0-9a-f]{12}_b\.(?:metal|json)|pso_manifest\.tsv)", name)):
                raise ValueError(f"unsafe shader seed path: {name}")
            if digest((seed / name).read_bytes()) != expected:
                raise ValueError(f"shader seed integrity mismatch: {name}")
        return report
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid recorded shader seed: {error}") from error


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
    parser.add_argument("--recorded-cache", type=Path, action="append",
                        help="external Mario shader cache from a played session; package verified variants and precompiled libraries")
    parser.add_argument("--static-seed", type=Path,
                        help="external verified static shader seed prepared from this Mario RomFS")
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
    seed = libs = None
    inputs = []
    for recorded in args.recorded_cache or []:
        cache = require(external(recorded))
        identity = recorded_cache_identity(cache)
        prepared = work / "development" / f"recorded-seed-{identity}"
        if not prepared.exists():
            prepare_recorded_seed(cache, prepared)
        verify_recorded_seed(prepared)
        inputs.append(prepared)
    if args.static_seed:
        static = require(external(args.static_seed))
        static_report = verify_recorded_seed(static)
        romfs_hash = json.loads((work / "update/romfs/index.json").read_text())["romfs_sha256"]
        if static_report.get("source_romfs_sha256") != romfs_hash:
            raise ValueError("static shader seed was prepared from a different RomFS")
        inputs.append(static)
    if len(inputs) >= 2:
        identity = digest(b"".join((source / "seed-manifest.json").read_bytes() for source in inputs))[:16]
        seed = work / "development" / f"merged-shader-seed-{identity}"
        if not seed.exists():
            merge_shader_seeds(inputs, seed)
        verify_recorded_seed(seed)
    elif inputs:
        seed = inputs[0]
        report = verify_recorded_seed(seed)
    if seed:
        report = verify_recorded_seed(seed)
        libs = work / "development" / "recorded-shader-libs"
        built, failed = compile_recorded_libraries(seed, libs)
        print(f"shader seed: {report['shaders']} variants, {report.get('pipeline_rows', 0)} pipelines; "
              f"precompiled libraries {built}, fallback sources {failed}", flush=True)
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
    if seed:
        shutil.copytree(seed, game / "build/shader-seed", copy_function=shutil.copy2)
        bundle_libs = game / "build/shader-libs"
        bundle_libs.mkdir()
        for source in seed.glob("*_b.metal"):
            library = libs / f"{digest(source.read_bytes())}.metallib"
            if library.is_file():
                shutil.copy2(library, bundle_libs / library.name)
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
