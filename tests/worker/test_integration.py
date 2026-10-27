"""Application security only. These tests do NOT apply a systemd/OS sandbox."""

import http.client
import json
import secrets
import socket
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from control_plane.auth import ADMIN, Authenticator
from control_plane.backup import create_backup, restore_backup
from control_plane.capabilities import CPU_DIGEST
from control_plane.contracts import ExecutionResult, Problem, canonical, sha256
from control_plane.http_api import API
from control_plane.service import ControlPlane
from control_plane.worker_client import LocalClient
from pepeuch_worker import private_io
from pepeuch_worker.executor import CPUTextDigest
from pepeuch_worker.isolation import inspect, require_isolation
from support import HTTPFixture


class ApplicationIntegration(unittest.TestCase):
    def setUp(self):
        self.f = HTTPFixture(self)
        original = socket.getaddrinfo
        def loopback_only(host, *args, **kwargs):
            if host != "127.0.0.1":
                raise AssertionError("external network forbidden")
            return original(host, *args, **kwargs)
        guard = patch("socket.getaddrinfo", side_effect=loopback_only)
        guard.start()
        self.addCleanup(guard.stop)

    def state(self, mission):
        return self.f.app.get_mission(ADMIN, mission["id"])

    def call(self, method, path, data=None, *, admin=False, key=None):
        credential = (self.f.app.store.root / "secrets/admin.token").read_text().strip() if admin else self.f.key if key is None else key
        connection = http.client.HTTPConnection("127.0.0.1", self.f.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=None if data is None else canonical(data).encode(),
                               headers={"Authorization": "Bearer " + credential, "Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw)
        finally:
            connection.close()

    def test_cpu_api_approval_execution_and_immutable_download(self):
        code, mission = self.call("POST", "/api/v1/cpu-missions", {"operation_id": str(uuid4()), "title": "CPU",
            "objective": "Un texte UTF-8 é", "workspace_id": self.f.workspace}, admin=True)
        self.assertEqual(code, 201)
        self.assertEqual(mission["required_capability"], CPU_DIGEST)
        self.f.app.execution.approve(ADMIN, mission["id"], {"operation_id": str(uuid4())})
        self.assertEqual(self.f.runner().run_once(), "completed")
        result = self.state(mission)["results"][0]
        raw, _, digest = self.f.app.workspace.download(ADMIN, self.f.workspace, result["file_id"], result["version_id"])
        self.assertEqual(digest, sha256(raw))
        self.assertIn(sha256("Un texte UTF-8 é".encode()).encode(), raw)
        self.assertIs(result["provenance"]["simulated"], False)
        self.assertIs(result["provenance"]["ai_inference"], False)
        self.assertEqual(result["provenance"]["os_isolation"], "NOT VERIFIED")
        self.assertFalse(self.state(mission)["tasks"][0]["simulated"])
        self.assertFalse(self.f.app.dashboard(ADMIN)["simulation_only"])
        nodes = self.f.app.execution.nodes(ADMIN)
        node = next(n for n in nodes if n["id"] == self.f.identity)
        self.assertEqual(node["accepted_cpu_results"], 1)
        self.assertEqual(node["verified_simulated_executions"], 0)
        self.assertFalse(node["isolation"]["verified"])

    def test_creation_idempotence_and_explicit_immutable_intent_without_schema_change(self):
        data = {"operation_id": str(uuid4()), "title": "CPU", "objective": "Texte", "workspace_id": self.f.workspace}
        first = self.f.app.create_cpu_mission(ADMIN, data)
        self.assertEqual(first, self.f.app.create_cpu_mission(ADMIN, data))
        with self.assertRaises(Problem):
            self.f.app.create_mission(ADMIN, data)
        events = self.f.app.events(ADMIN, first["id"])
        self.assertEqual([e["details"] for e in events if e["type"] == "mission_execution_contract_v1"], [{"capability": CPU_DIGEST}])
        with self.f.app.store.transaction() as con:
            self.assertEqual([r[0] for r in con.execute("SELECT version FROM schema_migrations ORDER BY version")], [1, 2])

    def test_worker_denied_admin_sqlite_workspace_and_output_path_routes(self):
        for method, path, body in (("GET", "/api/v1/missions", None), ("GET", "/api/v1/workers", None),
                ("GET", f"/api/v1/workspaces/{self.f.workspace}/files", None),
                ("POST", "/api/v1/cpu-missions", {}), ("GET", "/secrets/admin.token", None),
                ("GET", "/app/index.sqlite3", None), ("POST", "/objects/../../outside", {})):
            code, _ = self.call(method, path, body)
            self.assertIn(code, (403, 404))
        for path in ("/api/v1/workspaces/x/files", "/secrets/admin.token", "/app/index.sqlite3", "/objects"):
            with self.assertRaises(Problem):
                self.f.client.call("GET", path)

    def test_cpu_file_references_and_unknown_input_paths_refused(self):
        for change in ({"authorized_files": ["v_" + "0" * 32]}, {"tools": ["shell"]}, {"path": "/etc/passwd"}, {"capability": "gpu"}):
            with self.assertRaises(Problem):
                self.f.cpu(**change)

    def test_revocation_after_claim_rejects_old_result_and_cached_claim(self):
        mission = self.f.cpu()
        request = self.f.claim()
        principal = self.f.principal()
        result = CPUTextDigest(self.f.configuration["limits"], wall=lambda: self.f.now).execute(request)
        self.f.app.revoke_worker(ADMIN, self.f.identity, {"operation_id": str(uuid4())})
        with self.assertRaises(Problem):
            self.f.app.execution.finish(principal, request["attempt_id"], result)
        self.assertEqual(self.call("POST", f"/api/v1/execution/{request['attempt_id']}/finish", result.to_dict())[0], 401)
        self.assertEqual(self.state(mission)["state"], "interrupted")
        self.assertEqual(self.state(mission)["results"], [])

    def test_rotation_in_flight_fences_epoch_even_with_new_credential(self):
        # Registry method invoked by the test to isolate the epoch race; real CLI is offline.
        mission = self.f.cpu()
        request = self.f.claim()
        old = self.f.principal()
        result = CPUTextDigest(self.f.configuration["limits"], wall=lambda: self.f.now).execute(request)
        rotated = self.f.app.registry.rotate(self.f.identity)
        new_key = (self.f.app.store.root / rotated["credential_file"]).read_text().strip()
        new = self.f.server.api.auth.authenticate("Bearer " + new_key)
        for principal in (old, new):
            with self.assertRaises(Problem):
                self.f.app.execution.finish(principal, request["attempt_id"], result)
        with self.assertRaises(Problem):
            self.f.app.execution.state(new, request["attempt_id"])
        self.assertEqual(self.state(mission)["results"], [])

    def test_expired_generation_late_result_rejected_and_manual_retry_distinct(self):
        mission = self.f.cpu()
        old = self.f.claim()
        result = CPUTextDigest(self.f.configuration["limits"], wall=lambda: self.f.now).execute(old)
        self.f.now = old["deadline"]
        with self.assertRaises(Problem):
            self.f.app.execution.finish(self.f.principal(), old["attempt_id"], result)
        self.f.app.execution.retry(ADMIN, mission["id"], {"operation_id": str(uuid4())})
        new = self.f.claim()
        self.assertNotEqual(old["generation"], new["generation"])
        self.assertNotEqual(old["attempt_id"], new["attempt_id"])
        self.assertEqual(self.state(mission)["results"], [])

    def test_other_worker_cannot_read_or_finish_attempt(self):
        self.f.cpu()
        request = self.f.claim()
        enrolled = self.f.app.registry.enroll(capabilities=[CPU_DIGEST])
        other_key = (self.f.app.store.root / enrolled["credential_file"]).read_text().strip()
        self.assertEqual(self.call("GET", f"/api/v1/execution/{request['attempt_id']}/state", key=other_key)[0], 404)

    def test_cancel_between_execution_and_publication(self):
        mission = self.f.cpu()
        executor = CPUTextDigest(self.f.configuration["limits"], wall=lambda: self.f.now)
        def cancelling(request):
            result = executor.execute(request)
            self.f.app.execution.cancel(ADMIN, mission["id"], {"operation_id": str(uuid4())})
            return result
        self.assertEqual(self.f.runner(executor=Mock(execute=cancelling)).run_once(), "cancelled")
        self.assertEqual(self.state(mission)["results"], [])

    def test_lost_claim_response_recovered_without_recomputation(self):
        mission = self.f.cpu()
        real = self.f.client.call
        def lost(method, path, data=None):
            real(method, path, data)
            raise Problem("backend_unavailable", 503)
        with patch.object(self.f.client, "call", side_effect=lost):
            with self.assertRaises(Problem):
                self.f.runner().run_once()
        executor = Mock()
        self.assertEqual(self.f.runner(executor=executor).run_once(recover=True), "interrupted")
        executor.execute.assert_not_called()
        self.assertEqual(len(self.state(mission)["attempts"]), 1)
        self.assertEqual(self.state(mission)["results"], [])

    def test_lost_finish_request_replays_durable_result_only(self):
        mission = self.f.cpu()
        real = self.f.client.call
        def disconnected(method, path, data=None):
            if path.endswith("/finish"):
                raise Problem("backend_unavailable", 503)
            return real(method, path, data)
        with patch.object(self.f.client, "call", side_effect=disconnected):
            with self.assertRaises(Problem):
                self.f.runner().run_once()
        before = private_io.load(self.f.worker_root)["result"]
        with self.assertRaises(Problem):
            self.f.runner().run_once()
        executor = Mock()
        self.assertEqual(self.f.runner(executor=executor).run_once(recover=True), "completed")
        executor.execute.assert_not_called()
        self.assertEqual(private_io.load(self.f.worker_root)["result"], before)
        self.assertEqual(len(self.state(mission)["results"]), 1)

    def test_lost_finish_ack_observes_terminal_state_without_duplicate(self):
        mission = self.f.cpu()
        real = self.f.client.call
        def lost(method, path, data=None):
            value = real(method, path, data)
            if path.endswith("/finish"):
                raise Problem("backend_unavailable", 503)
            return value
        with patch.object(self.f.client, "call", side_effect=lost):
            with self.assertRaises(Problem):
                self.f.runner().run_once()
        self.assertEqual(self.f.runner().run_once(recover=True), "completed")
        self.assertEqual(len(self.state(mission)["results"]), 1)

    def test_disconnection_before_claim_keeps_same_operation_for_explicit_recovery(self):
        self.f.cpu()
        with patch.object(self.f.client, "call", side_effect=Problem("backend_unavailable", 503)):
            with self.assertRaises(Problem):
                self.f.runner().run_once()
        first = private_io.load(self.f.worker_root)["claim_id"]
        self.assertEqual(self.f.runner().run_once(recover=True), "interrupted")
        self.assertEqual(private_io.load(self.f.worker_root)["claim_id"], first)

    def test_credential_rotation_cannot_rebind_pending_local_journal(self):
        self.f.cpu()
        with patch.object(self.f.client, "call", side_effect=Problem("backend_unavailable", 503)):
            with self.assertRaises(Problem):
                self.f.runner().run_once()
        with self.assertRaises(Problem):
            self.f.runner(key=secrets.token_urlsafe(32)).run_once(recover=True)

    def test_restart_after_claim_interrupts_without_reexecution(self):
        mission = self.f.cpu()
        executor = Mock()
        executor.execute.side_effect = SystemExit("synthetic crash")
        with self.assertRaises(SystemExit):
            self.f.runner(executor=executor).run_once()
        recovered_executor = Mock()
        self.assertEqual(self.f.runner(executor=recovered_executor).run_once(recover=True), "interrupted")
        recovered_executor.execute.assert_not_called()
        self.assertEqual(self.state(mission)["state"], "interrupted")

    def test_backend_restart_fences_pending_worker_result(self):
        mission = self.f.cpu()
        real = self.f.client.call
        def disconnected(method, path, data=None):
            if path.endswith("/finish"):
                raise Problem("backend_unavailable", 503)
            return real(method, path, data)
        with patch.object(self.f.client, "call", side_effect=disconnected):
            with self.assertRaises(Problem):
                self.f.runner().run_once()
        self.f.app.close()
        self.f.app = ControlPlane(self.f.root / "backend", clock=lambda: self.f.now)
        self.f.server.api = API(self.f.app)
        executor = Mock()
        self.assertEqual(self.f.runner(executor=executor).run_once(recover=True), "interrupted")
        executor.execute.assert_not_called()
        self.assertEqual(self.state(mission)["results"], [])

    def test_output_path_injection_and_wrong_generation_cannot_publish(self):
        self.f.cpu()
        request = self.f.claim()
        result = CPUTextDigest(self.f.configuration["limits"], wall=lambda: self.f.now).execute(request)
        result.outputs[0]["name"] = "../outside"
        with self.assertRaises(Problem):
            self.f.app.execution.finish(self.f.principal(), request["attempt_id"], result)
        result.outputs[0]["name"] = "resultat.md"
        late = ExecutionResult(result.attempt_id, "g_" + "0" * 32, result.status, result.outputs)
        with self.assertRaises(Problem):
            self.f.app.execution.finish(self.f.principal(), request["attempt_id"], late)
        self.assertEqual(self.f.app.workspace.list_files(ADMIN, self.f.workspace)["files"], [])

    def test_corrupt_or_duplicate_execution_intent_fails_closed(self):
        mission = self.f.cpu()
        with self.f.app.store.transaction() as con:
            self.f.app._audit(con, ADMIN, self.f.workspace, mission["id"], "mission_execution_contract_v1", {"capability": CPU_DIGEST})
        with self.assertRaises(Problem) as error:
            self.state(mission)
        self.assertEqual(error.exception.code, "invalid_mission_contract")

    def test_credential_cannot_change_worker_or_endpoint_on_pending_recovery(self):
        self.f.cpu()
        with patch.object(self.f.client, "call", side_effect=Problem("backend_unavailable", 503)):
            with self.assertRaises(Problem):
                self.f.runner().run_once()
        self.f.configuration["backend_url"] = "http://127.0.0.1:1"
        with self.assertRaises(Problem):
            self.f.runner().run_once(recover=True)

    def test_idle_and_done_journal_require_no_reexecution(self):
        self.assertEqual(self.f.runner().run_once(), "idle")
        self.assertEqual(self.f.runner().run_once(recover=True), "nothing_to_recover")

    def test_interruption_is_durable_and_does_not_erase_previous_result(self):
        previous = self.f.cpu()
        self.f.runner().run_once()
        result = self.state(previous)["results"][0]
        raw = self.f.app.workspace.download(ADMIN, self.f.workspace, result["file_id"], result["version_id"])
        mission = self.f.cpu()
        executor = Mock()
        executor.execute.side_effect = KeyboardInterrupt()
        self.assertEqual(self.f.runner(executor=executor).run_once(), "interrupted")
        self.assertEqual(self.state(mission)["results"], [])
        self.assertEqual(self.f.app.workspace.download(ADMIN, self.f.workspace, result["file_id"], result["version_id"]), raw)

    def test_cpu_failure_codes_do_not_cross_demo_contract(self):
        self.f.cpu()
        request = self.f.claim()
        for error in ("simulated_failure", "simulated_interruption"):
            result = ExecutionResult(request["attempt_id"], request["generation"], "failed" if error.endswith("failure") else "interrupted", [], error)
            with self.assertRaises(Problem):
                self.f.app.execution.finish(self.f.principal(), request["attempt_id"], result)

    def test_strict_mode_refuses_before_credential_or_network_and_never_claims_os_proof(self):
        report = inspect(self.f.configuration)
        self.assertEqual(report["status"], "NOT VERIFIED")
        self.assertIsNone(report["properties"]["network"]["enforced"])
        with self.assertRaises(Problem):
            require_isolation(self.f.configuration)
        command = [sys.executable, "-m", "pepeuch_worker", "run", "--worker-dir", str(self.f.worker_root),
                   "--credential-file", str(self.f.worker_root / "does-not-exist")]
        result = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"os_isolation_not_verified", result.stderr)
        self.assertIsNone(private_io.load(self.f.worker_root))

    def test_independent_cli_executes_with_only_own_directory_and_private_key(self):
        mission = self.f.cpu()
        result = subprocess.run([sys.executable, "-m", "pepeuch_worker", "run", "--worker-dir", str(self.f.worker_root),
                                 "--application-test"], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"completed", result.stdout)
        self.assertIn(b"NOT VERIFIED", result.stdout)
        self.assertEqual(self.state(mission)["state"], "completed")
        self.assertNotIn(self.f.key.encode(), result.stdout + result.stderr)
        admin = (self.f.app.store.root / "secrets/admin.token").read_bytes().strip()
        self.assertNotIn(admin, result.stdout + result.stderr)

    def test_cpu_result_and_intent_survive_backup_restore_and_keys_are_revoked(self):
        mission = self.f.cpu()
        self.f.runner().run_once()
        before = self.state(mission)
        events = self.f.app.events(ADMIN, mission["id"])
        self.f.app.close()
        create_backup(self.f.root / "backend", self.f.root / "backup")
        restore_backup(self.f.root / "backup", self.f.root / "restored")
        app = ControlPlane(self.f.root / "restored", clock=lambda: self.f.now)
        self.addCleanup(app.close)
        self.assertEqual(app.get_mission(ADMIN, mission["id"]), before)
        self.assertEqual(app.events(ADMIN, mission["id"]), events)
        with self.assertRaises(Problem):
            Authenticator(self.f.root / "restored").authenticate("Bearer " + self.f.key)
        result = before["results"][0]
        raw = app.workspace.download(ADMIN, self.f.workspace, result["file_id"], result["version_id"])[0]
        self.assertIn(sha256(mission["objective"].encode()).encode(), raw)
