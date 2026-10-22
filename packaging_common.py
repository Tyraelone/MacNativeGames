"""Small, game-independent file and path rules for native Mac App packaging."""

import hashlib
from pathlib import Path
import shutil
import subprocess


def outside_repository(path: Path, repository: Path) -> Path:
    """Resolve an output or work path, including existing parent symlinks."""
    resolved = path.expanduser().resolve()
    root = repository.resolve()
    if resolved == root or root in resolved.parents:
        raise ValueError(f"generated files must stay outside the source project: {resolved}")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def verified_file(path: Path, expected: str | None = None) -> str:
    """Require a regular, unlinked input and optionally its expected digest."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing regular input: {path}")
    actual = sha256_file(path)
    if expected is not None and actual != expected:
        raise ValueError(f"SHA-256 mismatch: {path}: {actual}")
    return actual


def clone_file(source: Path, target: Path) -> None:
    """Use an APFS clone where possible and a normal copy across volumes."""
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"missing regular input: {source}")
    if target.is_symlink():
        raise ValueError(f"output is a symlink: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["cp", "-c", str(source), str(target)], capture_output=True).returncode:
        shutil.copy2(source, target)
