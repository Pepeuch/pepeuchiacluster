from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_http_integration as b51
from control_plane.auth import ADMIN, WORKER, Authenticator
from control_plane.backup import create_backup, restore_backup
from control_plane.contracts import Problem, canonical, new_id, sha256
from control_plane.demo import FakeWorker
from control_plane.service import ControlPlane
from control_plane.storage import Store
from control_plane.worker_registry import WorkerRegistry, default_limits


class Workers(unittest.TestCase):
    def setUp(self):
        self.fixture = b51.HTTPIntegration()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def revoke(self, identity="fake-cpu", data=None):
        return self.fixture.call("POST", f"/api/v1/workers/{identity}/revoke", {"operation_id": str(uuid4())} if data is None else data)

    def running(self):
        mission = self.fixture.mission()
        self.fixture.approve(mission)
        request = self.fixture.client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})["request"]
        return mission, request

    def test_live_revoke_rejects_old_key_and_fences_running_attempt(self):
        mission, request = self.running()
        self.assertEqual(self.revoke()[0], 200)
        result = FakeWorker().execute(request).to_dict()
        self.assertEqual(self.fixture.call("POST", f"/api/v1/execution/{request['attempt_id']}/finish", result, credential="worker")[0], 401)
        observed = self.fixture.app.get_mission(ADMIN, mission["id"])
        self.assertEqual(observed["state"], "interrupted")
        self.assertEqual(observed["attempts"][0]["error_code"], "worker_revoked")
        self.assertEqual(observed["results"], [])

    def test_authenticated_before_revocation_still_cannot_publish(self):
        _, request = self.running()
        principal = self.fixture.server.api.auth.authenticate("Bearer " + self.fixture.worker)
        self.revoke()
        with self.assertRaises(Problem):
            self.fixture.app.execution.finish(principal, request["attempt_id"], FakeWorker().execute(request))

    def test_revocation_is_idempotent_and_worker_cannot_revoke(self):
        data = {"operation_id": str(uuid4())}
        first = self.revoke(data=data)
        self.assertEqual(first[1], self.revoke(data=data)[1])
        self.assertEqual(self.fixture.call("POST", "/api/v1/workers/fake-cpu/revoke", data, credential="worker")[0], 401)

    def test_worker_cannot_use_admin_identity_api(self):
        self.assertEqual(self.fixture.call("GET", "/api/v1/workers", credential="worker")[0], 403)
        self.assertEqual(self.fixture.call("POST", "/api/v1/workers/fake-cpu/revoke", {"operation_id": str(uuid4())}, credential="worker")[0], 403)

    def test_registry_does_not_disclose_credentials_or_digests(self):
        public = self.fixture.call("GET", "/api/v1/workers")[1]
        self.assertNotIn(self.fixture.worker, str(public))
        self.assertNotIn(sha256(self.fixture.worker.encode()), str(public))
        self.assertNotIn(str(self.fixture.root), str(public))

    def test_offline_rotation_preserves_id_but_invalidates_key_and_epoch(self):
        old_key = self.fixture.worker
        old_auth = self.fixture.server.api.auth
        self.fixture.stop()
        store = Store(self.fixture.root)
        try:
            registry = WorkerRegistry(store, lambda: 2000)
            rotated = registry.rotate("fake-cpu")
        finally:
            store.close()
        new_key = (self.fixture.root / rotated["credential_file"]).read_text().strip()
        self.fixture.start()
        self.assertEqual(rotated["worker"]["id"], "fake-cpu")
        self.assertEqual(rotated["worker"]["credential_epoch"], 2)
        self.assertNotEqual(old_key, new_key)
        with self.assertRaises(Problem):
            old_auth.authenticate("Bearer " + old_key)
        principal = self.fixture.server.api.auth.authenticate("Bearer " + new_key)
        self.assertEqual(principal.credential_epoch, 2)
        with self.assertRaises(Problem):
            self.fixture.app.execution.claim(WORKER, {"operation_id": str(uuid4())})

    def test_revoked_identity_requires_explicit_reactivation_with_new_key(self):
        self.revoke()
        self.fixture.stop()
        store = Store(self.fixture.root)
        try:
            registry = WorkerRegistry(store, lambda: 2000)
            with self.assertRaises(Problem):
                registry.rotate("fake-cpu")
            renewed = registry.rotate("fake-cpu", reactivate=True)
        finally:
            store.close()
        self.fixture.start()
        self.assertEqual(renewed["worker"]["status"], "active")
        self.assertGreater(renewed["worker"]["credential_epoch"], 2)
        self.assertEqual(self.fixture.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())}, credential="worker")[0], 401)

    def test_new_identity_only_receives_declared_demo_capability(self):
        record = self.fixture.app.registry.enroll()
        self.assertNotEqual(record["worker"]["id"], "fake-cpu")
        key = (self.fixture.root / record["credential_file"]).read_text().strip()
        self.revoke()
        mission = self.fixture.mission()
        approved = self.fixture.approve(mission)
        self.assertEqual(approved["plan"]["worker_id"], record["worker"]["id"])
        code, body, _ = self.fixture.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())}, credential=key)
        self.assertEqual(code, 200)
        result = FakeWorker().execute(body["request"]).to_dict()
        self.assertEqual(self.fixture.call("POST", f"/api/v1/execution/{body['request']['attempt_id']}/finish", result, credential=key)[0], 200)

    def test_unsupported_capabilities_and_unenforced_resources_not_accepted(self):
        registry = self.fixture.app.registry
        for capabilities in (["shell"], ["demo.report.v1", "gpu"], []):
            with self.assertRaises(Problem):
                registry.enroll(capabilities=capabilities)
        for changes in ({"max_concurrent_tasks": 2}, {"lease_seconds": 0}, {"max_output_bytes": 65537}, {"ram_bytes": 1024}, {"max_output_bytes": False}):
            limits = default_limits(self.fixture.app.store.settings)
            limits.update(changes)
            with self.assertRaises(Problem):
                registry.enroll(limits=limits)

    def test_declared_output_limit_and_deadline_are_enforced(self):
        limits = {"max_concurrent_tasks": 1, "lease_seconds": 2, "max_output_bytes": 16}
        record = self.fixture.app.registry.enroll(limits=limits)
        self.revoke()
        mission = self.fixture.mission()
        self.fixture.approve(mission)
        key = (self.fixture.root / record["credential_file"]).read_text().strip()
        principal = self.fixture.server.api.auth.authenticate("Bearer " + key)
        request = self.fixture.app.execution.claim(principal, {"operation_id": str(uuid4())})["request"]
        self.assertEqual(request["deadline"] - self.fixture.now, 2)
        with self.assertRaises(Problem) as error:
            self.fixture.app.execution.finish(principal, request["attempt_id"], FakeWorker().execute(request))
        self.assertEqual(error.exception.code, "file_too_large")
        self.fixture.now = request["deadline"]
        self.assertEqual(self.fixture.app.get_mission(ADMIN, mission["id"])["state"], "interrupted")

    def test_cached_claim_cannot_bypass_revocation(self):
        self.fixture.approve(self.fixture.mission())
        operation = {"operation_id": str(uuid4())}
        self.fixture.app.execution.claim(WORKER, operation)
        self.revoke()
        with self.assertRaises(Problem):
            self.fixture.app.execution.claim(WORKER, operation)

    def test_another_enrolled_worker_cannot_finish_or_read_first_workers_attempt(self):
        _, request = self.running()
        record = self.fixture.app.registry.enroll()
        key = (self.fixture.root / record["credential_file"]).read_text().strip()
        status = self.fixture.call("GET", f"/api/v1/execution/{request['attempt_id']}/state", credential=key)[0]
        self.assertEqual(status, 404)
        self.assertEqual(self.fixture.call("POST", f"/api/v1/execution/{request['attempt_id']}/finish", FakeWorker().execute(request).to_dict(), credential=key)[0], 404)

    def test_cli_rotation_refuses_live_backend_then_new_credential_runs(self):
        command = [sys.executable, "-m", "control_plane", "worker-rotate", "--data-dir", str(self.fixture.root), "--worker-id", "fake-cpu"]
        refused = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(refused.returncode, 1)
        self.fixture.stop()
        accepted = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(accepted.returncode, 0)
        data = json.loads(accepted.stdout)
        credential_file = self.fixture.root / data["credential_file"]
        self.assertNotIn(credential_file.read_bytes().strip(), accepted.stdout + accepted.stderr)
        self.fixture.start()
        worker = subprocess.run([sys.executable, "-m", "control_plane", "worker", "--data-dir", str(self.fixture.root), "--credential-file", str(credential_file),
                                 "--server-url", f"http://127.0.0.1:{self.fixture.port}", "--once"], capture_output=True, timeout=10)
        self.assertEqual(worker.returncode, 0)
        self.assertIn(b"idle", worker.stdout)

    def test_restored_registry_stays_revoked_across_restart(self):
        self.fixture.stop()
        backup = self.fixture.root.parent / ("backup-" + uuid4().hex)
        restored = self.fixture.root.parent / ("restore-" + uuid4().hex)
        # Independently owned temporary siblings, cleanup only these exact paths.
        import shutil
        self.addCleanup(lambda: shutil.rmtree(backup) if backup.exists() else None)
        self.addCleanup(lambda: shutil.rmtree(restored) if restored.exists() else None)
        create_backup(self.fixture.root, backup)
        restore_backup(backup, restored)
        app = ControlPlane(restored, clock=lambda: 2000)
        try:
            self.assertEqual(app.registry.list()[0]["status"], "revoked")
            with self.assertRaises(Problem):
                Authenticator(restored).authenticate("Bearer " + self.fixture.worker)
        finally:
            app.close()
        app = ControlPlane(restored, clock=lambda: 3000)
        try:
            self.assertEqual(app.registry.list()[0]["status"], "revoked")
        finally:
            app.close()
        self.fixture.start()


class MigrationCompatibility(unittest.TestCase):
    def test_unsupported_sqlite_refused_before_creating_any_data(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b52-sqlite-version-") as temporary:
            destination = Path(temporary) / "new-data"
            with patch("control_plane.storage.sqlite3.sqlite_version_info", (3, 30, 1)):
                with self.assertRaises(Problem):
                    Store(destination)
            self.assertFalse(destination.exists())

    def test_restoring_pre_registry_backup_never_reactivates_legacy_worker(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b52-v1-restore-") as temporary:
            root = Path(temporary)
            migration = Path(__file__).resolve().parents[2] / "control_plane/migrations/0001.sql"
            with patch("control_plane.storage.Path.glob", return_value=[migration]):
                source = Store(root / "source")
            source.close()
            create_backup(root / "source", root / "backup")
            restore_backup(root / "backup", root / "restored")
            app = ControlPlane(root / "restored", clock=lambda: 2000)
            try:
                self.assertEqual(app.registry.list()[0]["status"], "revoked")
                new_unregistered_key = (root / "restored/secrets/worker.token").read_text().strip()
                with self.assertRaises(Problem):
                    Authenticator(root / "restored").authenticate("Bearer " + new_unregistered_key)
            finally:
                app.close()

    def test_b51_index_and_cached_worker_operation_upgrade_without_identity_changes(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b52-v1-") as temporary:
            root = Path(temporary)
            migration = Path(__file__).resolve().parents[2] / "control_plane/migrations/0001.sql"
            with patch("control_plane.storage.Path.glob", return_value=[migration]):
                store = Store(root)
            identity, operation = new_id("m"), {"operation_id": str(uuid4())}
            with store.transaction() as con:
                workspace = con.execute("SELECT id FROM workspaces").fetchone()[0]
                con.execute("INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?)", (identity, "local-admin", "local-project", workspace, "B5.1 intact", "Objectif existant", "draft", "2026-10-27T00:00:00+00:00", "[]"))
                request_hash = sha256(canonical({"action": "claim", "payload": operation}).encode())
                con.execute("INSERT INTO operations VALUES (?,?,?,?)", ("fake-cpu", operation["operation_id"], request_hash, '{"request":null}'))
                before = tuple(con.execute("SELECT * FROM missions").fetchone())
            store.close()
            app = ControlPlane(root, clock=lambda: 1000)
            try:
                with app.store.transaction() as con:
                    self.assertEqual(tuple(con.execute("SELECT * FROM missions").fetchone()), before)
                    self.assertEqual([r[0] for r in con.execute("SELECT version FROM schema_migrations ORDER BY version")], [1, 2])
                self.assertEqual(app.execution.claim(WORKER, operation), {"request": None})
                self.assertEqual(app.get_mission(ADMIN, identity)["id"], identity)
            finally:
                app.close()
