"""Deterministic regressions, not OS isolation tests; private /tmp fixtures only."""

import json
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane.contracts import Problem
from pepeuch_worker import private_io
from pepeuch_worker.contracts import SecurityProperty, require_verified
from pepeuch_worker.runner import IndependentRunner
from pepeuch_worker.__main__ import main


class AuditFixes(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b531-audit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_parent_replacement_cannot_redirect_read_after_validation(self):
        selected, outside = self.root / "selected", self.root / "outside"
        selected.mkdir(mode=0o700)
        outside.mkdir(mode=0o700)
        private_io.create(selected / "data", b"authorized")
        private_io.create(outside / "data", b"outside")
        original = os.open
        swapped = []
        def race(path, *args, **kwargs):
            if Path(path).name == "data" and not swapped:
                swapped.append(True)
                selected.rename(self.root / "retired")
                selected.symlink_to(outside, target_is_directory=True)
            return original(path, *args, **kwargs)
        with patch("os.open", side_effect=race):
            self.assertEqual(private_io.read(selected / "data", 32), b"authorized")

    def test_parent_replacement_cannot_redirect_file_creation(self):
        selected, outside = self.root / "selected", self.root / "outside"
        selected.mkdir(mode=0o700)
        outside.mkdir(mode=0o700)
        original = os.open
        swapped = []
        def race(path, *args, **kwargs):
            if Path(path).name == "created" and not swapped:
                swapped.append(True)
                selected.rename(self.root / "retired")
                selected.symlink_to(outside, target_is_directory=True)
            return original(path, *args, **kwargs)
        with patch("os.open", side_effect=race):
            private_io.create(selected / "created", b"authorized")
        self.assertFalse((outside / "created").exists())
        self.assertEqual((self.root / "retired/created").read_bytes(), b"authorized")

    def test_temporary_collision_preserves_unowned_existing_file(self):
        path = self.root / ".journal-collision"
        private_io.create(path, b"preserve")
        with patch("pepeuch_worker.private_io.uuid4", return_value=SimpleNamespace(hex="collision")):
            with self.assertRaises(FileExistsError):
                private_io.save(self.root, {"a": 1})
        self.assertEqual(path.read_bytes(), b"preserve")

    def test_lock_is_validated_and_locked_on_the_same_descriptor(self):
        private_io.create(self.root / "run.lock", b"")
        original = os.open
        opened = []
        def count(path, *args, **kwargs):
            if Path(path).name == "run.lock":
                opened.append(True)
            return original(path, *args, **kwargs)
        with patch("os.open", side_effect=count):
            with private_io.locked(self.root):
                pass
        self.assertEqual(len(opened), 1)

    def test_one_self_declared_true_property_cannot_grant_isolation(self):
        with self.assertRaises(Problem):
            require_verified({"invented": SecurityProperty("anything", True, True, "worker supplied")})

    def test_runner_copies_validated_configuration(self):
        data = json.loads(Path("deploy/worker-linux/worker-config.example.json").read_text())
        client, executor = Mock(), Mock()
        runner = IndependentRunner(self.root, data, "x" * 43, client, executor)
        data["worker_id"] = "n_" + "1" * 32
        data["limits"]["seconds"] = 999
        self.assertNotEqual(runner.config["worker_id"], data["worker_id"])
        self.assertEqual(runner.config["limits"]["seconds"], 30)

    def test_initialization_parent_race_never_creates_directory_outside_anchor(self):
        selected, outside = self.root / "selected", self.root / "outside"
        selected.mkdir(mode=0o700)
        outside.mkdir(mode=0o700)
        config = self.root / "config.json"
        config.write_bytes(Path("deploy/worker-linux/worker-config.example.json").read_bytes())
        original = os.mkdir
        def race(path, *args, **kwargs):
            if Path(path).name == "instance":
                selected.rename(self.root / "retired")
                selected.symlink_to(outside, target_is_directory=True)
            return original(path, *args, **kwargs)
        argv = ["pepeuch_worker", "init", "--worker-dir", str(selected / "instance"), "--configuration-file", str(config)]
        with patch("sys.argv", argv), patch("os.mkdir", side_effect=race), redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 1)  # Changed pathname is refused after anchored creation.
        self.assertFalse((outside / "instance").exists())
        self.assertTrue((self.root / "retired/instance").is_dir())
