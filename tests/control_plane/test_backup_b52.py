import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from control_plane.auth import ADMIN, WORKER, Authenticator
from control_plane.backup import create_backup, inspect_backup, restore_backup
from control_plane.contracts import Problem, canonical, sha256
from control_plane.demo import FakeWorker
from control_plane.service import ControlPlane
from control_plane.storage import Store, write_new
from control_plane.workspace import WorkspaceManager


class Backups(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b52-backup-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.backup, self.restored = (self.root / name for name in ("source", "backup", "restored"))
        self.app = ControlPlane(self.source, clock=lambda: 1000)
        self.addCleanup(self.app.close)
        self.workspace = self.app.workspaces(ADMIN)[0]["id"]
        mission = self.app.create_mission(ADMIN, {"operation_id": str(uuid4()), "workspace_id": self.workspace, "title": "Backup", "objective": "Démonstration persistante"})
        self.identity = mission["id"]
        self.app.execution.approve(ADMIN, self.identity, {"operation_id": str(uuid4())})
        request = self.app.execution.claim(WORKER, {"operation_id": str(uuid4())})["request"]
        self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request))
        self.mission = self.app.get_mission(ADMIN, self.identity)
        result = self.mission["results"][0]
        self.file_id, self.version = result["file_id"], result["version_id"]
        self.bytes = self.app.workspace.download(ADMIN, self.workspace, self.file_id, self.version)[0]

    def save(self):
        self.app.close()
        return create_backup(self.source, self.backup)

    def refresh_manifest_digest(self, relative):
        path = self.backup / "manifest.json"
        manifest = json.loads(path.read_text())
        raw = (self.backup / relative).read_bytes()
        for entry in manifest["files"]:
            if entry["path"] == relative:
                entry.update(size=len(raw), sha256=sha256(raw))
        path.write_text(canonical(manifest))

    def test_complete_backup_restore_restart_same_mission_events_and_download(self):
        events = self.app.events(ADMIN, self.identity)
        self.save()
        restore_backup(self.backup, self.restored)
        restored = ControlPlane(self.restored, clock=lambda: 2000)
        self.addCleanup(restored.close)
        self.assertEqual(restored.get_mission(ADMIN, self.identity), self.mission)
        self.assertEqual(restored.events(ADMIN, self.identity), events)
        raw = restored.workspace.download(ADMIN, self.workspace, self.file_id, self.version)[0]
        self.assertEqual(raw, self.bytes)
        restored.close()
        restored = ControlPlane(self.restored, clock=lambda: 3000)
        self.addCleanup(restored.close)
        self.assertEqual(restored.workspace.download(ADMIN, self.workspace, self.file_id, self.version)[2], sha256(self.bytes))

    def test_running_backend_blocks_backup_without_creating_target(self):
        with self.assertRaises(Problem):
            create_backup(self.source, self.backup)
        self.assertFalse(self.backup.exists())

    def test_credentials_not_copied_and_old_tokens_refused_after_restore(self):
        old = [(self.source / f"secrets/{role}.token").read_bytes().strip() for role in ("admin", "worker")]
        self.save()
        for path in self.backup.rglob("*"):
            if path.is_file():
                for credential in old:
                    self.assertNotIn(credential, path.read_bytes())
        restore_backup(self.backup, self.restored)
        auth = Authenticator(self.restored)
        for credential in old:
            with self.assertRaises(Problem):
                auth.authenticate("Bearer " + credential.decode())

    def test_existing_restore_target_even_empty_is_preserved(self):
        self.save()
        self.restored.mkdir(mode=0o700)
        note = self.restored / "user-data"
        note.write_text("preserve")
        with self.assertRaises(Problem):
            restore_backup(self.backup, self.restored)
        self.assertEqual(note.read_text(), "preserve")

    def test_existing_backup_is_not_overwritten_or_pruned(self):
        self.save()
        first = (self.backup / "manifest.json").read_bytes()
        with self.assertRaises(Problem):
            create_backup(self.source, self.backup)
        self.assertEqual((self.backup / "manifest.json").read_bytes(), first)

    def test_corrupt_or_missing_object_refused_before_destination_created(self):
        self.save()
        obj = next((self.backup / "objects").iterdir())
        obj.write_bytes(b"corrupt")
        with self.assertRaises(Problem):
            restore_backup(self.backup, self.restored)
        self.assertFalse(self.restored.exists())

    def test_truncated_index_and_manifest_refused(self):
        self.save()
        (self.backup / "app/index.sqlite3").write_bytes(b"SQLite truncated")
        with self.assertRaises(Problem):
            inspect_backup(self.backup)
        (self.backup / "manifest.json").write_bytes(b"{")
        with self.assertRaises(Problem):
            inspect_backup(self.backup)

    def test_references_checked_even_with_recomputed_manifest_digest(self):
        self.save()
        with sqlite3.connect(self.backup / "app/index.sqlite3") as con:
            con.execute("UPDATE versions SET sha256=?", ("0" * 64,))
        self.refresh_manifest_digest("app/index.sqlite3")
        with self.assertRaises(Problem):
            inspect_backup(self.backup)

    def test_unexpected_schema_trigger_not_accepted(self):
        self.save()
        with sqlite3.connect(self.backup / "app/index.sqlite3") as con:
            con.execute("CREATE TRIGGER unexpected AFTER INSERT ON missions BEGIN SELECT 1; END")
        self.refresh_manifest_digest("app/index.sqlite3")
        with self.assertRaises(Problem):
            inspect_backup(self.backup)

    def test_unsafe_name_not_accepted_from_modified_index(self):
        self.save()
        with sqlite3.connect(self.backup / "app/index.sqlite3") as con:
            con.execute("UPDATE files SET name=?", ("../../secret",))
        self.refresh_manifest_digest("app/index.sqlite3")
        with self.assertRaises(Problem):
            inspect_backup(self.backup)

    def test_symlink_object_and_destination_refused(self):
        self.save()
        obj = next((self.backup / "objects").iterdir())
        obj.unlink()
        obj.symlink_to(self.source / "secrets/admin.token")
        with self.assertRaises(Problem):
            restore_backup(self.backup, self.restored)
        with self.assertRaises(Problem):
            create_backup(self.source, self.source / "descendant")

    def test_extra_secret_path_and_manifest_traversal_refused(self):
        self.save()
        path = self.backup / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["files"][0]["path"] = "../source/secrets/admin.token"
        path.write_text(canonical(manifest))
        with self.assertRaises(Problem):
            inspect_backup(self.backup)

    def test_interruption_before_backup_commit_marker_retains_source(self):
        self.app.close()
        original = (self.source / "app/index.sqlite3").read_bytes()
        def interrupted(path, raw):
            if path.name == "manifest.json":
                raise KeyboardInterrupt()
            return write_new(path, raw)
        with patch("control_plane.backup.write_new", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                create_backup(self.source, self.backup)
        with self.assertRaises(Problem):
            inspect_backup(self.backup)
        self.assertEqual((self.source / "app/index.sqlite3").read_bytes(), original)

    def test_interrupted_restore_is_not_accepted_as_installation(self):
        self.save()
        def interrupted(path, raw):
            if path == self.restored / "config/installation.json":
                raise KeyboardInterrupt()
            return write_new(path, raw)
        with patch("control_plane.backup.write_new", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                restore_backup(self.backup, self.restored)
        with self.assertRaises(Problem):
            Store(self.restored)
        self.assertEqual((self.source / "objects" / sha256(self.bytes)).read_bytes(), self.bytes)

    def test_hot_journal_refused_and_unreferenced_objects_not_exported(self):
        self.app.close()
        journal = self.source / "app/index.sqlite3-journal"
        journal.write_bytes(b"interrupted")
        with self.assertRaises(Problem):
            create_backup(self.source, self.backup)
        journal.unlink()
        orphan = self.source / "objects" / ("0" * 64)
        orphan.write_bytes(b"unreferenced synthetic test data")
        create_backup(self.source, self.backup)
        self.assertTrue(orphan.exists())
        self.assertFalse((self.backup / "objects" / orphan.name).exists())

    def test_backup_is_private_and_does_not_modify_source_index(self):
        self.app.close()
        before = (self.source / "app/index.sqlite3").read_bytes()
        create_backup(self.source, self.backup)
        self.assertEqual((self.source / "app/index.sqlite3").read_bytes(), before)
        self.assertEqual(self.backup.stat().st_mode & 0o077, 0)
        self.assertFalse((self.backup / "secrets").exists())
