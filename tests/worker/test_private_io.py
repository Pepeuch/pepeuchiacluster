import os
from pathlib import Path
import secrets
import tempfile
import unittest

from control_plane.contracts import Problem
from pepeuch_worker import private_io


class PrivateIO(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b53-private-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_private_credential_and_readonly_systemd_credential(self):
        path = self.root / "credential"
        key = secrets.token_urlsafe(32)
        private_io.create(path, key.encode() + b"\n")
        self.assertEqual(private_io.credential(path), key)
        path.chmod(0o400)
        self.assertEqual(private_io.credential(path), key)

    def test_public_hardlinked_symlink_fifo_and_oversized_credentials_refused(self):
        path = self.root / "credential"
        private_io.create(path, secrets.token_urlsafe(32).encode())
        path.chmod(0o644)
        with self.assertRaises(Problem):
            private_io.credential(path)
        path.chmod(0o600)
        alias = self.root / "alias"
        os.link(path, alias)
        with self.assertRaises(Problem):
            private_io.credential(path)
        alias.unlink()
        alias.symlink_to(path)
        with self.assertRaises(Problem):
            private_io.credential(alias)
        alias.unlink()
        os.mkfifo(alias, 0o600)
        with self.assertRaises(Problem):
            private_io.credential(alias)
        alias.unlink()
        private_io.create(alias, b"x" * 129)
        with self.assertRaises(Problem):
            private_io.credential(alias)

    def test_atomic_journal_is_private_and_durable(self):
        private_io.save(self.root, {"a": 1})
        private_io.save(self.root, {"a": 2})
        self.assertEqual(private_io.load(self.root), {"a": 2})
        self.assertEqual((self.root / "run.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.glob(".journal-*")), [])

    def test_journal_cannot_write_through_link_outside_its_root(self):
        target = self.root / "outside"
        private_io.create(target, b"preserved")
        (self.root / "run.json").symlink_to(target)
        with self.assertRaises(Problem):
            private_io.save(self.root, {"bad": True})
        self.assertEqual(target.read_bytes(), b"preserved")

    def test_exclusive_worker_lock(self):
        with private_io.locked(self.root):
            with self.assertRaises(Problem):
                with private_io.locked(self.root):
                    self.fail("concurrent run")

    def test_nonprivate_and_symlink_directory_refused(self):
        directory = self.root / "public"
        directory.mkdir(mode=0o755)
        with self.assertRaises(Problem):
            private_io.directory(directory)
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(Problem):
            private_io.directory(link)
