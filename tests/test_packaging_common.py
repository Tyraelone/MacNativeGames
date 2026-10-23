"""Contracts shared by the three native game packagers (synthetic files only)."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import packaging_common


class PackagingCommonTests(unittest.TestCase):
    def test_output_path_rejects_repository_and_parent_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            (root / "shortcut").symlink_to(repository, target_is_directory=True)
            for path in (repository / "Game.app", root / "shortcut/Game.app"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    packaging_common.outside_repository(path, repository)
            self.assertEqual(packaging_common.outside_repository(root / "Game.app", repository), (root / "Game.app").resolve())

    def test_output_path_rejects_other_worktree_of_same_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current, other = root / "current", root / "other"
            current.mkdir()
            other.mkdir()
            with mock.patch.object(packaging_common, "_git_worktree_roots",
                                   return_value=(current.resolve(), other.resolve())):
                with self.assertRaisesRegex(ValueError, "outside the source project"):
                    packaging_common.outside_repository(other / "generated", current)

    def test_clone_preserves_bytes_when_apfs_clone_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / "source.bin", root / "nested/destination.bin"
            source.write_bytes(b"synthetic game data\x00")
            with mock.patch.object(packaging_common.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
                packaging_common.clone_file(source, destination)
            self.assertEqual(destination.read_bytes(), b"synthetic game data\x00")
            self.assertEqual(packaging_common.sha256_file(destination), hashlib.sha256(b"synthetic game data\x00").hexdigest())

    def test_verified_file_rejects_symlink_and_wrong_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            source.write_bytes(b"original")
            (root / "link.bin").symlink_to(source)
            with self.assertRaises(ValueError):
                packaging_common.verified_file(root / "link.bin")
            with self.assertRaises(ValueError):
                packaging_common.verified_file(source, "0" * 64)
            self.assertEqual(packaging_common.verified_file(source), hashlib.sha256(b"original").hexdigest())


if __name__ == "__main__":
    unittest.main()
