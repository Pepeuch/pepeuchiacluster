from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from control_plane.auth import ADMIN, WORKER
from control_plane.contracts import Problem
from control_plane.http_api import API, LocalServer
from control_plane.service import ControlPlane


class APIFoundations(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b51-api-")
        self.addCleanup(temporary.cleanup)
        self.app = ControlPlane(Path(temporary.name), clock=lambda: 1000)
        self.addCleanup(self.app.close)
        self.api = API(self.app)

    def test_health_and_mission_routes(self):
        self.assertEqual(self.api.dispatch("GET", "/api/v1/health", ADMIN).body["status"], "ok")
        workspace = self.api.dispatch("GET", "/api/v1/workspaces", ADMIN).body["workspaces"][0]["id"]
        response = self.api.dispatch("POST", "/api/v1/missions", ADMIN, {"operation_id": str(uuid4()), "workspace_id": workspace, "title": "Test", "objective": "Test"})
        self.assertEqual(response.status, 201)
        identity = response.body["id"]
        self.assertEqual(self.api.dispatch("GET", "/api/v1/missions/" + identity, ADMIN).body["state"], "draft")
        self.assertEqual(len(self.api.dispatch("GET", "/api/v1/missions/" + identity + "/events", ADMIN).body["events"]), 1)

    def test_worker_cannot_read_admin_routes(self):
        for path in ("/api/v1/health", "/api/v1/missions", "/api/v1/workspaces"):
            with self.assertRaises(Problem):
                self.api.dispatch("GET", path, WORKER)

    def test_lan_listener_refused_before_socket_creation(self):
        with self.assertRaises(Problem):
            LocalServer(self.api, host="0.0.0.0")
