import base64
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from control_plane.auth import ADMIN, WORKER
from control_plane.contracts import Principal, Problem, sha256
from control_plane.demo import FakeWorker
from control_plane.http_api import API
from control_plane.service import ControlPlane
from control_plane.storage import Settings, write_new


def payload(raw=b"hello", name="document.txt", expected=None):
    return {"operation_id": str(uuid4()), "name": name, "content_base64": base64.b64encode(raw).decode(),
            "size": len(raw), "sha256": sha256(raw), "expected_version": expected}


class Workspaces(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pepeuch-b51-files-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = ControlPlane(self.root, clock=lambda: 1000)
        self.addCleanup(self.app.close)
        self.workspace = self.app.workspaces(ADMIN)[0]["id"]

    def upload(self, **kwargs):
        return self.app.workspace.upload(ADMIN, self.workspace, payload(**kwargs))

    def request(self):
        mission = self.app.create_mission(ADMIN, {"operation_id": str(uuid4()), "workspace_id": self.workspace, "title": "Démo persistante", "objective": "Produire un rapport de démonstration."})
        self.app.execution.approve(ADMIN, mission["id"], {"operation_id": str(uuid4())})
        return self.app.execution.claim(WORKER, {"operation_id": str(uuid4())})["request"]

    def finish(self, request):
        return self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request))

    def test_upload_list_download_and_immutable_versions(self):
        first = self.upload()
        second = self.upload(raw=b"updated", expected=first["version_id"])
        self.assertEqual(first["file_id"], second["file_id"])
        self.assertNotEqual(first["version_id"], second["version_id"])
        self.assertEqual(self.app.workspace.download(ADMIN, self.workspace, first["file_id"], first["version_id"])[0], b"hello")
        self.assertEqual(self.app.workspace.download(ADMIN, self.workspace, second["file_id"])[0], b"updated")
        listed = self.app.workspace.list_files(ADMIN, self.workspace)
        self.assertEqual([v["number"] for v in listed["files"][0]["versions"]], [2, 1])
        self.assertEqual(listed["used_bytes"], 12)

    def test_upload_idempotent_without_extra_version(self):
        data = payload()
        first = self.app.workspace.upload(ADMIN, self.workspace, data)
        self.assertEqual(first, self.app.workspace.upload(ADMIN, self.workspace, data))
        self.assertEqual(len(self.app.workspace.list_files(ADMIN, self.workspace)["files"][0]["versions"]), 1)

    def test_concurrent_version_conflict_preserves_previous_content(self):
        first = self.upload()
        self.upload(raw=b"winner", expected=first["version_id"])
        with self.assertRaises(Problem):
            self.upload(raw=b"loser", expected=first["version_id"])
        self.assertEqual(self.app.workspace.download(ADMIN, self.workspace, first["file_id"])[0], b"winner")

    def test_path_traversal_and_reserved_names(self):
        for name in ("../private", "/etc/passwd", "a/b", "a\\b", "a\x00.txt", "..", "CON", "a.", "<script>.txt", "a\r\nb.txt"):
            with self.subTest(name=name), self.assertRaises(Problem):
                self.upload(name=name)
        self.assertEqual(self.app.workspace.list_files(ADMIN, self.workspace)["files"], [])

    def test_size_digest_encoding_and_unknown_fields(self):
        for changes in ({"size": 99}, {"size": False}, {"sha256": "0" * 64}, {"content_base64": "%%"}, {"secret": "redacted-synthetic-marker"}):
            data = payload()
            data.update(changes)
            with self.assertRaises(Problem):
                self.app.workspace.upload(ADMIN, self.workspace, data)

    def test_file_too_large(self):
        with self.assertRaises(Problem) as error:
            self.upload(raw=b"x" * (1_048_576 + 1))
        self.assertEqual(error.exception.status, 413)

    def test_quota_counts_all_versions(self):
        self.app.store.settings = Settings(max_file_bytes=10, quota_bytes=9)
        first = self.upload(raw=b"12345")
        with self.assertRaises(Problem) as error:
            self.upload(raw=b"67890", expected=first["version_id"])
        self.assertEqual(error.exception.code, "workspace_quota_exceeded")
        self.assertEqual(self.app.workspace.download(ADMIN, self.workspace, first["file_id"])[0], b"12345")

    def test_cross_project_listing_upload_and_download_denied(self):
        file = self.upload()
        foreign = Principal("another-user", "admin")
        for operation in (lambda: self.app.workspace.list_files(foreign, self.workspace),
                          lambda: self.app.workspace.upload(foreign, self.workspace, payload()),
                          lambda: self.app.workspace.download(foreign, self.workspace, file["file_id"]),
                          lambda: self.app.workspace.download(WORKER, self.workspace, file["file_id"])):
            with self.assertRaises(Problem):
                operation()

    def test_authorized_input_versions_are_frozen(self):
        file = self.upload()
        mission = self.app.create_mission(ADMIN, {"operation_id": str(uuid4()), "workspace_id": self.workspace, "title": "x", "objective": "x", "authorized_files": [file["version_id"]]})
        self.upload(raw=b"new", expected=file["version_id"])
        self.assertEqual(self.app.get_mission(ADMIN, mission["id"])["authorized_files"], [file["version_id"]])

    def test_partial_staging_rejected_and_old_version_intact(self):
        first = self.upload()
        with patch("control_plane.workspace.write_new", side_effect=lambda path, raw: write_new(path, raw[:1])):
            with self.assertRaises(Problem):
                self.upload(raw=b"second", expected=first["version_id"])
        self.assertEqual(self.app.workspace.download(ADMIN, self.workspace, first["file_id"])[0], b"hello")
        self.assertEqual(list((self.root / "staging").iterdir()), [])

    def test_interruption_before_atomic_object_publish_keeps_old_version(self):
        first = self.upload()
        with patch("control_plane.workspace.os.replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.upload(raw=b"new", expected=first["version_id"])
        self.assertEqual(self.app.workspace.download(ADMIN, self.workspace, first["file_id"])[0], b"hello")

    def test_corrupt_object_and_symlink_are_refused(self):
        file = self.upload()
        obj = self.root / "objects" / file["sha256"]
        obj.write_bytes(b"bad")
        with self.assertRaises(Problem):
            self.app.workspace.download(ADMIN, self.workspace, file["file_id"])
        obj.unlink()
        obj.symlink_to(self.root / "secrets" / "admin.token")
        with self.assertRaises(OSError):
            self.app.workspace.download(ADMIN, self.workspace, file["file_id"])

    def test_complete_only_after_publication(self):
        request = self.request()
        with patch.object(self.app.workspace, "_object", side_effect=OSError("redacted-failure")):
            with self.assertRaises(OSError):
                self.finish(request)
        mission = self.app.get_mission(ADMIN, request["mission"]["id"])
        self.assertEqual(mission["state"], "running")
        self.assertEqual(mission["results"], [])
        self.finish(request)
        self.assertEqual(self.app.get_mission(ADMIN, request["mission"]["id"])["state"], "completed")

    def test_end_to_end_result_survives_restart_with_same_sha_and_audit(self):
        request = self.request()
        self.finish(request)
        identity = request["mission"]["id"]
        mission = self.app.get_mission(ADMIN, identity)
        result = mission["results"][0]
        first = self.app.workspace.download(ADMIN, self.workspace, result["file_id"], result["version_id"])
        events = self.app.events(ADMIN, identity)
        self.app.close()
        self.app = ControlPlane(self.root, clock=lambda: 2000)
        self.addCleanup(self.app.close)
        second = self.app.workspace.download(ADMIN, self.workspace, result["file_id"], result["version_id"])
        self.assertEqual(first, second)
        self.assertEqual(sha256(second[0]), second[2])
        self.assertEqual(self.app.events(ADMIN, identity), events)
        self.assertEqual(self.app.get_mission(ADMIN, identity)["state"], "completed")

    def test_duplicate_result_response_and_modified_repeat(self):
        request = self.request()
        self.assertFalse(self.finish(request)["duplicate"])
        events = self.app.events(ADMIN, request["mission"]["id"])
        self.assertTrue(self.finish(request)["duplicate"])
        self.assertEqual(self.app.events(ADMIN, request["mission"]["id"]), events)
        result = FakeWorker().execute(request)
        result.outputs[0]["sha256"] = "0" * 64
        with self.assertRaises(Problem):
            self.app.execution.finish(WORKER, request["attempt_id"], result)

    def test_stale_expected_output_version_cannot_overwrite_upload(self):
        request = self.request()
        uploaded = self.upload(raw=b"keep", name="resultat.md")
        with self.assertRaises(Problem) as error:
            self.finish(request)
        self.assertEqual(error.exception.code, "version_conflict")
        self.assertEqual(self.app.workspace.download(ADMIN, self.workspace, uploaded["file_id"])[0], b"keep")
        self.assertEqual(self.app.get_mission(ADMIN, request["mission"]["id"])["state"], "running")

    def test_wrong_output_digest_never_completes(self):
        request = self.request()
        result = FakeWorker().execute(request)
        result.outputs[0]["sha256"] = "0" * 64
        with self.assertRaises(Problem):
            self.app.execution.finish(WORKER, request["attempt_id"], result)
        self.assertEqual(self.app.get_mission(ADMIN, request["mission"]["id"])["results"], [])

    def test_download_api_is_attachment_and_has_no_host_path(self):
        file = self.upload()
        api = API(self.app)
        response = api.dispatch("GET", f"/api/v1/workspaces/{self.workspace}/files/{file['file_id']}/download", ADMIN)
        self.assertEqual(response.body, b"hello")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertNotIn(str(self.root), str(api.dispatch("GET", f"/api/v1/workspaces/{self.workspace}/files", ADMIN).body))

    def test_unfinished_staging_is_not_listed_restored_or_deleted(self):
        residue = self.root / "staging" / "interrupted-process"
        residue.write_bytes(b"partial")
        self.app.close()
        self.app = ControlPlane(self.root, clock=lambda: 1000)
        self.addCleanup(self.app.close)
        self.assertEqual(self.app.workspace.list_files(ADMIN, self.workspace)["files"], [])
        self.assertEqual(residue.read_bytes(), b"partial")

    def test_interruption_after_object_fsync_before_database_commit(self):
        request = self.request()
        actual_transition = self.app._transition
        def interrupt(con, principal, row, target, **kwargs):
            if target == "completed":
                raise KeyboardInterrupt()
            return actual_transition(con, principal, row, target, **kwargs)
        with patch.object(self.app, "_transition", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.finish(request)
        self.assertEqual(self.app.workspace.list_files(ADMIN, self.workspace)["files"], [])
        self.assertEqual(self.app.get_mission(ADMIN, request["mission"]["id"])["state"], "running")
        self.finish(request)
        self.assertEqual(self.app.get_mission(ADMIN, request["mission"]["id"])["state"], "completed")
        self.assertEqual(len(self.app.workspace.list_files(ADMIN, self.workspace)["files"][0]["versions"]), 1)

    def test_actual_concurrent_uploads_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        first = self.upload()
        def attempt(raw):
            try:
                return self.upload(raw=raw, expected=first["version_id"])
            except Problem as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, (b"one", b"two")))
        self.assertEqual(sum(isinstance(result, dict) for result in outcomes), 1)
        self.assertIn("version_conflict", outcomes)
        self.assertEqual(len(self.app.workspace.list_files(ADMIN, self.workspace)["files"][0]["versions"]), 2)
