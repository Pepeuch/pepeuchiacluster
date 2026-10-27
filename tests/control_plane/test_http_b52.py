"""Wire-level regressions, no provider traffic or user data."""

import http.client
import io
import json
import socket
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_http_integration as b51
from control_plane.auth import ADMIN
from control_plane.contracts import Problem
from control_plane.http_io import DeadlineInput, ResponseInput
from control_plane.worker_client import LocalClient, WorkerRunner


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.fixture = b51.HTTPIntegration()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def raw(self, raw, *, eof=True):
        with socket.create_connection(("127.0.0.1", self.fixture.port), timeout=2) as connection:
            connection.sendall(raw)
            if eof:
                connection.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                try:
                    chunk = connection.recv(65536)
                except ConnectionResetError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks)

    def request(self, headers=b"", body=b"", *, line=b"GET / HTTP/1.1\r\n"):
        return line + f"Host: 127.0.0.1:{self.fixture.port}\r\n".encode() + headers + b"\r\n" + body

    def code(self, raw):
        return int(raw.split(b" ", 2)[1])

    def test_obsolete_folding_whitespace_and_non_ascii_headers(self):
        for header in (b"X-Test : nope\r\n", b"X-Test: one\r\n two\r\n", b"X-Test: \x80\r\n", b"X-Test: \0\r\n", b"X-Test:\tvalue\r\n"):
            with self.subTest(header=header):
                self.assertEqual(self.code(self.raw(self.request(header))), 400)

    def test_duplicate_and_ambiguous_lengths(self):
        for header in (b"Content-Length: 0\r\ncontent-length: 0\r\n", b"Content-Length: 0, 0\r\n", b"Content-Length: +0\r\n", b"Content-Length: -1\r\n", b"Content-Length: 0\r\nTransfer-Encoding: chunked\r\n"):
            self.assertEqual(self.code(self.raw(self.request(header))), 400)

    def test_duplicate_auth_host_and_origin_are_rejected_before_static_response(self):
        for header in (b"host: attacker.test\r\n", b"Authorization: x\r\nAuthorization: y\r\n", b"Origin: x\r\norigin: x\r\n"):
            response = self.raw(self.request(header))
            self.assertEqual(self.code(response), 400)
            self.assertNotIn(self.fixture.admin.encode(), response)

    def test_header_line_count_total_and_request_line_limits(self):
        for raw, expected in ((self.request(b"X-Test: " + b"a" * 4096 + b"\r\n"), 431),
                              (self.request(b"".join(f"X-{n}: value\r\n".encode() for n in range(32))), 431),
                              (self.request(b"".join(f"X-{n}: ".encode() + b"a" * 3500 + b"\r\n" for n in range(5))), 431),
                              (self.request(line=b"GET /" + b"a" * 2048 + b" HTTP/1.1\r\n"), 414)):
            self.assertEqual(self.code(self.raw(raw)), expected)

    def test_lone_lf_partial_headers_and_http09_not_accepted(self):
        for raw in (b"GET / HTTP/1.1\nHost: x\n\n", b"GET /\r\n", b"GET / HTTP/1.1\r\nHost: unfinished", b"GET  / HTTP/1.1\r\n\r\n"):
            self.assertEqual(self.code(self.raw(raw)), 400)

    def test_incomplete_body_cannot_create_mission(self):
        headers = ("Authorization: Bearer " + self.fixture.admin + "\r\nContent-Length: 100\r\nContent-Type: application/json\r\n").encode()
        response = self.raw(self.request(headers, b"{}", line=b"POST /api/v1/missions HTTP/1.1\r\n"))
        self.assertEqual(self.code(response), 400)
        self.assertEqual(self.fixture.app.list_missions(ADMIN), [])

    def test_timeout_is_bounded_and_connection_slot_recovers(self):
        self.fixture.server.io_seconds = 0.02
        response = self.raw(b"GET / HTTP/1.1\r\n", eof=False)
        self.assertEqual(self.code(response), 408)
        self.fixture.server.io_seconds = 5
        self.assertEqual(self.fixture.call("GET", "/api/v1/health")[0], 200)

    def test_saturated_connection_budget_refuses_and_then_recovers(self):
        semaphore = self.fixture.server.slots = threading.BoundedSemaphore(1)
        semaphore.acquire()
        try:
            self.assertEqual(self.raw(self.request()), b"")
        finally:
            semaphore.release()
        self.assertEqual(self.code(self.raw(self.request())), 200)

    def test_static_get_cannot_bypass_framing_and_head_has_no_body(self):
        self.assertEqual(self.code(self.raw(self.request(b"Content-Length: 1\r\n", b"x"))), 400)
        head = self.raw(self.request(line=b"HEAD / HTTP/1.1\r\n"))
        self.assertEqual(self.code(head), 405)
        self.assertEqual(head.split(b"\r\n\r\n", 1)[1], b"")

    def test_expect_upgrade_absolute_uri_and_control_targets_refused(self):
        for raw in (self.request(b"Expect: 100-continue\r\n"), self.request(b"Upgrade: websocket\r\n"),
                    self.request(line=b"GET http://attacker.test/ HTTP/1.1\r\n"), self.request(line=b"GET /\x00 HTTP/1.1\r\n")):
            self.assertIn(self.code(self.raw(raw)), (400, 417))

    def test_pipelining_never_creates_second_mission(self):
        def create():
            body = json.dumps({"operation_id": str(uuid4()), "workspace_id": self.fixture.workspace, "title": "test", "objective": "test"}).encode()
            headers = f"Authorization: Bearer {self.fixture.admin}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n".encode()
            return self.request(headers, body, line=b"POST /api/v1/missions HTTP/1.1\r\n")
        self.raw(create() + create())
        self.assertEqual(len(self.fixture.app.list_missions(ADMIN)), 1)

    def test_parse_errors_also_have_no_store_and_security_headers(self):
        response = self.raw(b"broken-secret-placeholder\r\n")
        self.assertIn(b"Cache-Control: no-store", response)
        self.assertIn(b"X-Content-Type-Options: nosniff", response)
        self.assertNotIn(b"broken-secret-placeholder", response)


class FakeSocket:
    def __init__(self, frames, clock):
        self.frames = iter(frames)
        self.clock = clock
        self.timeouts = []
    def settimeout(self, value):
        self.timeouts.append(value)
    def recv(self, _limit):
        elapsed, raw = next(self.frames)
        self.clock[0] += elapsed
        return raw


class ReaderContracts(unittest.TestCase):
    def test_drip_feed_cannot_reset_absolute_deadline(self):
        clock = [0.0]
        connection = FakeSocket([(0.6, b"a"), (0.6, b"\n")], clock)
        reader = DeadlineInput(connection, seconds=1, clock=lambda: clock[0])
        with self.assertRaises(TimeoutError):
            reader.readline(20)
        self.assertLess(connection.timeouts[1], connection.timeouts[0])

    def test_complete_body_arriving_after_deadline_is_not_accepted(self):
        clock = [0.0]
        reader = DeadlineInput(FakeSocket([(2, b"{}")], clock), seconds=1, clock=lambda: clock[0])
        with self.assertRaises(TimeoutError):
            reader.read(2)

    def test_response_headers_are_bounded_and_require_crlf(self):
        for line in (b"HTTP/1.1 200 OK\n", b"X: " + b"a" * 4097 + b"\r\n"):
            clock = [0.0]
            reader = ResponseInput(FakeSocket([(0, line)], clock), clock=lambda: clock[0])
            with self.assertRaises(OSError):
                reader.readline(65537)

    def test_worker_rejects_ambiguous_compressed_or_truncated_responses(self):
        for wire in (b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\nContent-Type: application/json; charset=utf-8\r\n\r\n{}',
                     b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\nContent-Type: application/json; charset=utf-8\r\n\r\n{}',
                     b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Encoding: gzip\r\nContent-Type: application/json; charset=utf-8\r\n\r\n{}'):
            class StreamSocket:
                def makefile(self, mode):
                    return io.BytesIO(wire)
            response = http.client.HTTPResponse(StreamSocket())
            response.begin()
            with patch("control_plane.worker_client.LocalConnection") as connection:
                connection.return_value.getresponse.return_value = response
                with self.assertRaises(Problem):
                    LocalClient("http://127.0.0.1:8765", "synthetic-value").call("POST", "/api/v1/execution/claim", {})


class WorkerReplyContracts(unittest.TestCase):
    def request(self):
        from control_plane.contracts import new_id
        mission = new_id("m")
        return {"schema": "pepeuch.control-plane/execution-request/v1", "attempt_id": new_id("a"), "generation": new_id("g"),
                "mission": {"id": mission, "title": "test", "objective": "test"},
                "task": {"schema": "pepeuch.control-plane/task/v1", "id": new_id("t"), "mission_id": mission,
                         "role": "demo-report", "capability": "demo.report.v1", "worker_id": "fake-cpu", "state": "running", "simulated": True},
                "authorized_files": [], "started_at": "2026-10-27T00:00:00+00:00", "deadline": 2000, "expected_version": None}

    def test_invalid_claim_envelope_cannot_execute(self):
        from unittest.mock import Mock
        client, executor = Mock(), Mock()
        client.call.return_value = {"unexpected": "redacted-private-value"}
        with self.assertRaises(Problem):
            WorkerRunner(client, executor).run_once()
        executor.execute.assert_not_called()

    def test_wrong_identity_or_capability_cannot_execute(self):
        from unittest.mock import Mock
        for mutate in (lambda r: r["task"].update(capability="shell"), lambda r: r["task"].update(mission_id="other")):
            request = self.request()
            mutate(request)
            client, executor = Mock(), Mock()
            client.call.return_value = {"request": request}
            with self.assertRaises(Problem):
                WorkerRunner(client, executor).run_once()
            executor.execute.assert_not_called()

    def test_untrusted_state_is_not_returned_for_diagnostics(self):
        from unittest.mock import Mock
        client, executor = Mock(), Mock()
        client.call.side_effect = [{"request": self.request()}, {"schema": "pepeuch.control-plane/attempt-state/v1", "state": "redacted-private-value", "deadline": 2000}]
        with self.assertRaises(Problem) as error:
            WorkerRunner(client, executor).run_once()
        self.assertNotIn("redacted-private-value", str(error.exception))
        executor.execute.assert_not_called()

    def test_mismatched_acknowledgement_is_not_reported_as_success(self):
        from unittest.mock import Mock
        client = Mock()
        client.call.side_effect = [{"request": self.request()}, {"schema": "pepeuch.control-plane/attempt-state/v1", "state": "running", "deadline": 2000},
                                   {"accepted": True, "duplicate": False, "mission_id": "wrong-mission"}]
        with self.assertRaises(Problem):
            WorkerRunner(client).run_once()
