from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from control_plane.auth import ADMIN, WORKER
from control_plane.contracts import Principal, Problem
from control_plane.demo import FakeWorker
from control_plane.service import ControlPlane


def operation():
    return {"operation_id": str(uuid4())}


class Executions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pepeuch-b51-exec-")
        self.addCleanup(self.temp.cleanup)
        self.now = 1000.0
        self.root = Path(self.temp.name)
        self.app = ControlPlane(self.root, clock=lambda: self.now)
        self.addCleanup(self.app.close)
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen", "time.sleep"):
            guard = patch(target, side_effect=AssertionError("No real execution or network"))
            guard.start()
            self.addCleanup(guard.stop)

    def mission(self, approve=True):
        workspace = self.app.workspaces(ADMIN)[0]["id"]
        mission = self.app.create_mission(ADMIN, {**operation(), "title": "Démo", "objective": "$(touch /tmp/do-not-execute) <script>test</script>", "workspace_id": workspace})
        if approve:
            mission = self.app.execution.approve(ADMIN, mission["id"], operation())
        return mission

    def claim(self):
        return self.app.execution.claim(WORKER, operation())["request"]

    def test_approval_plan_and_running_are_distinct(self):
        mission = self.mission()
        self.assertEqual(mission["state"], "queued")
        self.assertEqual(mission["plan"]["capability"], "demo.report.v1")
        self.assertEqual(mission["tasks"][0]["role"], "demo-report")
        self.assertTrue(mission["plan"]["simulated"])
        request = self.claim()
        self.assertEqual(self.app.get_mission(ADMIN, mission["id"])["state"], "running")
        self.assertEqual(request["schema"], "pepeuch.control-plane/execution-request/v1")
        states = [e["details"]["state"] for e in self.app.events(ADMIN, mission["id"]) if "state" in e["details"]]
        self.assertEqual(states, ["draft", "approved", "queued", "running"])

    def test_approval_is_explicit(self):
        self.mission(approve=False)
        self.assertIsNone(self.claim())

    def test_approval_double_submission_idempotent(self):
        mission = self.mission(approve=False)
        request = operation()
        first = self.app.execution.approve(ADMIN, mission["id"], request)
        self.assertEqual(first, self.app.execution.approve(ADMIN, mission["id"], request))
        with self.assertRaises(Problem):
            self.app.execution.approve(ADMIN, mission["id"], operation())
        self.assertEqual(len(first["tasks"]), 1)

    def test_worker_claim_repetition_and_single_capacity(self):
        self.mission()
        self.mission()
        operation_data = operation()
        first = self.app.execution.claim(WORKER, operation_data)
        self.assertEqual(first, self.app.execution.claim(WORKER, operation_data))
        self.assertIsNone(self.claim())

    def test_simulation_is_deterministic_and_never_executes_prompt(self):
        self.mission()
        request = self.claim()
        first = FakeWorker().execute(request)
        self.assertEqual(first, FakeWorker().execute(deepcopy(request)))
        import base64
        content = base64.b64decode(first.outputs[0]["content_base64"]).decode()
        self.assertIn("SIMULATION", content)
        self.assertIn("$(touch /tmp/do-not-execute)", content)
        self.assertIn(request["attempt_id"], content)

    def test_failure_and_interruption(self):
        for mode, state in (("fail", "failed"), ("interrupt", "interrupted")):
            mission = self.mission()
            request = self.claim()
            self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request, mode=mode))
            observed = self.app.get_mission(ADMIN, mission["id"])
            self.assertEqual(observed["state"], state)
            self.assertEqual(observed["results"], [])

    def test_cancel_before_execution(self):
        mission = self.mission()
        result = self.app.execution.cancel(ADMIN, mission["id"], operation())
        self.assertEqual(result["state"], "cancelled")
        self.assertIsNone(self.claim())

    def test_cancel_running_requires_ack_and_refuses_late_success(self):
        mission = self.mission()
        request = self.claim()
        observed = self.app.execution.cancel(ADMIN, mission["id"], operation())
        self.assertEqual(observed["state"], "cancel_requested")
        with self.assertRaises(Problem):
            self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request))
        self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request, mode="cancel"))
        self.assertEqual(self.app.get_mission(ADMIN, mission["id"])["state"], "cancelled")

    def test_expiration_does_not_publish_or_retry(self):
        mission = self.mission()
        request = self.claim()
        self.now = request["deadline"]
        with self.assertRaises(Problem):
            self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request))
        observed = self.app.get_mission(ADMIN, mission["id"])
        self.assertEqual(observed["state"], "interrupted")
        self.assertEqual(observed["attempts"][0]["error_code"], "attempt_expired")
        self.assertIsNone(self.claim())

    def test_restart_fences_inflight_and_rejects_old_generation(self):
        mission = self.mission()
        request = self.claim()
        self.app.close()
        self.app = ControlPlane(self.root, clock=lambda: self.now)
        self.addCleanup(self.app.close)
        observed = self.app.get_mission(ADMIN, mission["id"])
        self.assertEqual(observed["state"], "interrupted")
        self.assertEqual(observed["attempts"][0]["error_code"], "backend_restart")
        with self.assertRaises(Problem):
            self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request))

    def test_retry_is_manual_and_new_attempt_has_distinct_identity(self):
        mission = self.mission()
        first = self.claim()
        self.app.execution.finish(WORKER, first["attempt_id"], FakeWorker().execute(first, mode="fail"))
        self.assertIsNone(self.claim())
        self.app.execution.retry(ADMIN, mission["id"], operation())
        second = self.claim()
        self.assertNotEqual(first["attempt_id"], second["attempt_id"])
        self.assertNotEqual(first["generation"], second["generation"])
        attempts = self.app.get_mission(ADMIN, mission["id"])["attempts"]
        self.assertEqual([a["number"] for a in attempts], [1, 2])

    def test_completed_requires_durable_publisher(self):
        self.mission()
        request = self.claim()
        with patch.object(self.app, "workspace", None, create=True):
            with self.assertRaises(Problem):
                self.app.execution.finish(WORKER, request["attempt_id"], FakeWorker().execute(request))
        self.assertEqual(self.app.get_mission(ADMIN, request["mission"]["id"])["state"], "running")

    def test_wrong_worker_or_generation_refused(self):
        self.mission()
        request = self.claim()
        result = FakeWorker().execute(request, mode="fail")
        for principal, changed in ((Principal("different-worker", "worker"), result), (WORKER, replace(result, generation="g_" + "0" * 32))):
            with self.assertRaises(Problem):
                self.app.execution.finish(principal, request["attempt_id"], changed)

    def test_simulated_nodes_do_not_claim_real_hardware_validation(self):
        node = self.app.execution.nodes(ADMIN)[0]
        self.assertTrue(node["simulated"])
        self.assertFalse(node["hardware_verified"])
        self.assertFalse(node["online_verified"])
        self.assertIsNone(node["gpu"])

    def test_coordinator_failure_leaves_draft_unchanged(self):
        mission = self.mission(approve=False)
        with patch.object(self.app.execution.coordinator, "plan", side_effect=Problem("no_declared_capability", 409)):
            with self.assertRaises(Problem):
                self.app.execution.approve(ADMIN, mission["id"], operation())
        observed = self.app.get_mission(ADMIN, mission["id"])
        self.assertEqual(observed["state"], "draft")
        self.assertEqual(observed["tasks"], [])
