"""Real loopback HTTP, isolated data, injected execution clock; no provider calls."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
import http.client
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from control_plane.auth import ADMIN
from control_plane.contracts import Problem, sha256
from control_plane.demo import FakeWorker
from control_plane.http_api import API, LocalServer, Response
from control_plane.service import ControlPlane
from control_plane.worker_client import LocalClient, WorkerRunner


class HTTPIntegration(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b51-http-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.now = 1000.0
        self.start()
        self.addCleanup(self.stop)
        original = socket.getaddrinfo
        def local_only(host, *args, **kwargs):
            if host != "127.0.0.1":
                raise AssertionError("External network forbidden")
            return original(host, *args, **kwargs)
        guard = patch("socket.getaddrinfo", side_effect=local_only)
        guard.start()
        self.addCleanup(guard.stop)

    def start(self):
        self.app = ControlPlane(self.root, clock=lambda: self.now)
        try:
            self.server = LocalServer(API(self.app), port=0)
        except BaseException:
            self.app.close()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.port = self.server.server_port
        self.admin = (self.root / "secrets/admin.token").read_text().strip()
        self.worker = (self.root / "secrets/worker.token").read_text().strip()
        self.client = LocalClient(f"http://127.0.0.1:{self.port}", self.worker)
        self.workspace = self.app.workspaces(ADMIN)[0]["id"]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.app.close()

    def call(self, method, path, data=None, *, credential="admin", headers=None, raw=None):
        auth = {} if credential is None else {"Authorization": "Bearer " + (self.admin if credential == "admin" else self.worker if credential == "worker" else credential)}
        body = json.dumps(data).encode() if data is not None else raw
        values = {**auth, **({"Content-Type": "application/json"} if body is not None else {}), **({} if headers is None else headers)}
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            content = response.read()
            parsed = json.loads(content) if response.getheader("Content-Type", "").startswith("application/json") else content
            return response.status, parsed, dict(response.getheaders())
        finally:
            connection.close()

    def mission(self):
        status, mission, _ = self.call("POST", "/api/v1/missions", {"operation_id": str(uuid4()), "workspace_id": self.workspace, "title": "Mission HTTP", "objective": "Rapport de démonstration."})
        self.assertEqual(status, 201)
        return mission

    def approve(self, mission):
        status, body, _ = self.call("POST", "/api/v1/missions/" + mission["id"] + "/approve", {"operation_id": str(uuid4())})
        self.assertEqual(status, 200)
        return body

    def test_http_complete_workflow_and_backend_worker_restart(self):
        mission = self.mission()
        self.assertEqual(mission["state"], "draft")
        self.assertEqual(self.approve(mission)["state"], "queued")
        self.assertEqual(WorkerRunner(self.client).run_once(), "completed")
        _, completed, _ = self.call("GET", "/api/v1/missions/" + mission["id"])
        result = completed["results"][0]
        path = f"/api/v1/workspaces/{self.workspace}/files/{result['file_id']}/versions/{result['version_id']}/download"
        code, first, headers = self.call("GET", path)
        self.assertEqual(code, 200)
        self.assertEqual(headers["X-Content-SHA256"], sha256(first))
        self.assertIn("SIMULATION", first.decode())
        _, events, _ = self.call("GET", "/api/v1/missions/" + mission["id"] + "/events")
        self.stop()
        self.start()
        self.assertEqual(self.call("GET", path)[1], first)
        self.assertEqual(self.call("GET", "/api/v1/missions/" + mission["id"])[1]["state"], "completed")
        self.assertEqual(self.call("GET", "/api/v1/missions/" + mission["id"] + "/events")[1], events)

    def test_cli_worker_is_separate_process_without_direct_business_database_access(self):
        self.approve(self.mission())
        result = subprocess.run([sys.executable, "-m", "control_plane", "worker", "--data-dir", str(self.root), "--server-url", f"http://127.0.0.1:{self.port}", "--once"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("completed", result.stdout)
        self.assertNotIn(self.admin, result.stdout + result.stderr)
        self.assertNotIn(self.worker, result.stdout + result.stderr)

    def test_authentication_missing_wrong_and_cookie_only(self):
        for credential, headers in ((None, {}), ("invalid", {}), (None, {"Cookie": "session=not-authorized"})):
            status, body, _ = self.call("GET", "/api/v1/missions", credential=credential, headers=headers)
            self.assertEqual(status, 401)
            self.assertEqual(body, {"error": "authentication_required"})

    def test_roles_are_enforced_for_both_api_domains(self):
        self.assertEqual(self.call("GET", "/api/v1/missions", credential="worker")[0], 403)
        self.assertEqual(self.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})[0], 403)
        self.assertEqual(self.call("POST", "/api/v1/execution/a_" + "0" * 32 + "/finish", {})[0], 403)

    def test_dns_rebinding_host_and_csrf_origin_refused(self):
        for headers in ({"Host": "attacker.test"}, {"Origin": "http://attacker.test"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.call("GET", "/api/v1/missions", headers=headers)[0], 403)

    def test_local_static_shell_has_security_headers_and_no_private_data(self):
        code, content, headers = self.call("GET", "/", credential=None)
        self.assertEqual(code, 200)
        self.assertIn(b"SIMULATION", content)
        self.assertNotIn(self.admin.encode(), content)
        self.assertNotIn(self.worker.encode(), content)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_malformed_json_rejected(self):
        for body in (b'{"title":"a","title":"b"}', b'{"size":NaN}', b'{"size":1e999}', b'\xff', b'{'):
            self.assertEqual(self.call("POST", "/api/v1/missions", raw=body)[0], 400)

    def test_header_body_limits_and_wrong_content_type(self):
        self.assertEqual(self.call("POST", "/api/v1/missions", headers={"Content-Length": "1500001"})[0], 413)
        self.assertEqual(self.call("POST", "/api/v1/missions", raw=b"{}", headers={"Content-Type": "text/plain"})[0], 415)

    def test_duplicate_lengths_and_transfer_encoding_refused(self):
        for pairs in ([('Content-Length', '2'), ('Content-Length', '2')], [('Transfer-Encoding', 'chunked')]):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                connection.putrequest("POST", "/api/v1/missions")
                connection.putheader("Authorization", "Bearer " + self.admin)
                for key, value in pairs:
                    connection.putheader(key, value)
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            finally:
                connection.close()

    def test_path_traversal_and_secret_files_are_not_served(self):
        for path in ("/../secrets/admin.token", "/%2e%2e/secrets/admin.token", "/objects", "/api/v1/missions?credential=hidden"):
            code, body, _ = self.call("GET", path)
            self.assertIn(code, (400, 404))
            self.assertNotIn(self.admin, str(body))
            self.assertNotIn(str(self.root), str(body))

    def test_result_failure_does_not_log_secrets_or_exception_text(self):
        self.approve(self.mission())
        request = self.client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})["request"]
        stderr = io.StringIO()
        marker = "private-path-or-credential-not-in-diagnostics"
        with redirect_stderr(stderr), patch.object(self.app.workspace, "_object", side_effect=OSError(marker)):
            code, body, _ = self.call("POST", f"/api/v1/execution/{request['attempt_id']}/finish", FakeWorker().execute(request).to_dict(), credential="worker")
        self.assertEqual(code, 500)
        self.assertEqual(body, {"error": "operation_failed"})
        self.assertNotIn(marker, stderr.getvalue() + str(body))
        self.assertNotIn(self.admin, stderr.getvalue())
        self.assertNotIn(self.worker, stderr.getvalue())

    def test_worker_handles_cancellation_before_compute(self):
        mission = self.mission()
        self.approve(mission)
        def cancel(_request):
            self.call("POST", "/api/v1/missions/" + mission["id"] + "/cancel", {"operation_id": str(uuid4())})
        self.assertEqual(WorkerRunner(self.client).run_once(before_execute=cancel), "cancelled")
        self.assertEqual(self.call("GET", "/api/v1/missions/" + mission["id"])[1]["state"], "cancelled")

    def test_two_actual_worker_clients_cannot_claim_same_task(self):
        self.approve(self.mission())
        def claim(_):
            client = LocalClient(f"http://127.0.0.1:{self.port}", self.worker)
            return client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})["request"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = list(pool.map(claim, range(2)))
        self.assertEqual(sum(request is not None for request in requests), 1)

    def test_worker_refuses_external_hosts_credentials_proxies_and_redirect_targets(self):
        for address in ("http://example.test:8765", "http://localhost:8765", "https://127.0.0.1:8765", "http://user@127.0.0.1:8765", "http://127.0.0.1:8765/other", "http://127.0.0.1:8765?x=1"):
            with self.assertRaises(Problem):
                LocalClient(address, "synthetic-value")

    def test_download_requires_auth_even_when_id_is_known(self):
        mission = self.mission()
        self.approve(mission)
        WorkerRunner(self.client).run_once()
        result = self.call("GET", "/api/v1/missions/" + mission["id"])[1]["results"][0]
        path = f"/api/v1/workspaces/{self.workspace}/files/{result['file_id']}/download"
        self.assertEqual(self.call("GET", path, credential=None)[0], 401)
        self.assertEqual(self.call("GET", path, credential="worker")[0], 403)

    def test_execution_result_schema_and_unknown_fields_refused(self):
        self.approve(self.mission())
        request = self.client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})["request"]
        for change in ({"schema": "pepeuch.control-plane/execution-result/v2"}, {"status": []}, {"unexpected": True}):
            result = FakeWorker().execute(request).to_dict()
            result.update(change)
            code, _, _ = self.call("POST", f"/api/v1/execution/{request['attempt_id']}/finish", result, credential="worker")
            self.assertEqual(code, 400)
        self.assertEqual(self.call("GET", "/api/v1/missions/" + request["mission"]["id"])[1]["state"], "running")

    def test_worker_does_not_forward_credentials_on_redirect(self):
        with patch.object(self.server.api, "dispatch", return_value=Response({}, 302, {"Location": "http://provider.invalid:8765"})) as dispatch:
            with self.assertRaises(Problem):
                self.client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})
        self.assertEqual(dispatch.call_count, 1)
