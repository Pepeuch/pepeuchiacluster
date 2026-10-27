from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from control_plane.auth import ADMIN, WORKER, Authenticator
from control_plane.contracts import Principal, Problem, decode_json
from control_plane.service import ControlPlane
from control_plane.storage import Store


class Foundations(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pepeuch-b51-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = ControlPlane(self.root, clock=lambda: 1000)
        self.addCleanup(self.app.close)
        self.workspace = self.app.workspaces(ADMIN)[0]["id"]

    def create(self, **changes):
        data = {"operation_id": str(uuid4()), "title": "Mission de test", "objective": "Créer un rapport simulé", "workspace_id": self.workspace}
        data.update(changes)
        return self.app.create_mission(ADMIN, data)

    def test_create_and_versioned_schemas(self):
        mission = self.create()
        self.assertEqual(mission["schema"], "pepeuch.control-plane/mission/v1")
        self.assertEqual(mission["workspace"]["schema"], "pepeuch.control-plane/workspace-reference/v1")
        self.assertEqual(mission["state"], "draft")
        self.assertEqual(mission["attempts"], [])
        self.assertEqual(self.app.events(ADMIN, mission["id"])[0]["schema"], "pepeuch.control-plane/audit-event/v1")

    def test_idempotence_and_conflicting_double_submission(self):
        operation = str(uuid4())
        first = self.create(operation_id=operation)
        self.assertEqual(first, self.create(operation_id=operation))
        with self.assertRaises(Problem):
            self.create(operation_id=operation, objective="Different")
        self.assertEqual(len(self.app.list_missions(ADMIN)), 1)

    def test_access_checks_for_other_owner_and_worker(self):
        mission = self.create()
        for principal in (Principal("another-owner", "admin"), WORKER):
            with self.assertRaises(Problem):
                self.app.get_mission(principal, mission["id"])
            with self.assertRaises(Problem):
                self.app.create_mission(principal, {"operation_id": str(uuid4()), "title": "x", "objective": "x", "workspace_id": self.workspace})

    def test_identity_requires_actual_credential_and_roles_differ(self):
        auth = Authenticator(self.root)
        for role, identity in (("admin", ADMIN), ("worker", WORKER)):
            token = (self.root / "secrets" / (role + ".token")).read_text().strip()
            self.assertEqual(auth.authenticate("Bearer " + token), identity)
        for header in (None, "", "Bearer nope", "Bearer é"):
            with self.assertRaises(Problem):
                auth.authenticate(header)

    def test_invalid_create_fields_and_oversized_objective(self):
        for changes in ({"objective": " "}, {"objective": "a" * 4001}, {"operation_id": "not-an-operation"}, {"authorized_files": ["../../private"]}, {"unknown": True}):
            with self.assertRaises(Problem):
                self.create(**changes)

    def test_restart_keeps_mission_and_audit(self):
        mission = self.create()
        events = self.app.events(ADMIN, mission["id"])
        self.app.close()
        self.app = ControlPlane(self.root, clock=lambda: 2000)
        self.addCleanup(self.app.close)
        self.assertEqual(self.app.get_mission(ADMIN, mission["id"]), mission)
        self.assertEqual(self.app.events(ADMIN, mission["id"]), events)

    def test_single_backend_lock(self):
        with self.assertRaises(Problem):
            Store(self.root)

    def test_unknown_migration_is_refused(self):
        with self.app.store.transaction() as con:
            con.execute("UPDATE schema_migrations SET sha256='corrupted'")
        self.app.close()
        with self.assertRaises(Problem):
            Store(self.root)

    def test_user_text_is_not_copied_to_audit(self):
        marker = "private-text-never-in-audit"
        mission = self.create(title=marker, objective=marker)
        self.assertNotIn(marker, str(self.app.events(ADMIN, mission["id"])))

    def test_strict_json(self):
        for data in ('{"a":1,"a":2}', '{"value": NaN}', b'\xff'):
            with self.assertRaises(Problem):
                decode_json(data)

    def test_unrecognized_directory_preserved(self):
        directory = self.root / "unrelated"
        directory.mkdir(mode=0o700)
        original = directory / "user-data"
        original.write_text("preserve")
        with self.assertRaises(Problem):
            Store(directory)
        self.assertEqual(original.read_text(), "preserve")

    def test_symlink_directory_refused(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(Problem):
            Store(alias)
