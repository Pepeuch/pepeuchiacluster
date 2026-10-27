from copy import deepcopy
import os
import socket
import struct
import unittest
from unittest.mock import MagicMock, Mock, patch

from control_plane.contracts import Problem, canonical
from pepeuch_worker.verification import CHECKS, digest
from pepeuch_worker.verification_channel import REPLY, VerificationSession, transfer, validate_decision
from pepeuch_worker.verifier import receive_authenticated_request, serve_diagnostic, unit_metadata
from fixtures import configuration, observations


def request():
    return {"nonce": "a" * 64, "configuration": configuration(), "context": observations()["process"]}


def reply():
    data = request()
    return {"schema": REPLY, "nonce": data["nonce"], "context_sha256": digest(data["context"]),
            "configuration_sha256": digest(data["configuration"]), "profile": configuration()["os_profile"]["schema"],
            "policy_sha256": "b" * 64, "receipt_sha256": "c" * 64, "issued_monotonic": 100,
            "expires_monotonic": 101, "decision": "permit",
            "guarantees": {name: {"enforced": True, "verified": True, "evidence_sha256": "d" * 64} for name in CHECKS}}


def framed_peer(data, credentials=(12, 0, 0)):
    raw = canonical(data).encode()
    stream = bytearray(struct.pack("!I", len(raw)) + raw)
    sock = Mock()
    def receive(size, ancsize):
        result = bytes(stream[:size])
        del stream[:size]
        return result, [(socket.SOL_SOCKET, socket.SCM_CREDENTIALS, struct.pack("3i", *credentials))], 0, None
    sock.recvmsg.side_effect = receive
    return sock


class Channel(unittest.TestCase):
    def test_01_missing_or_invalid_inherited_descriptor_refuses(self):
        for descriptor in (None, True, -1, 0, 1, 2, 1025):
            with self.assertRaises(Problem) as error:
                VerificationSession(configuration(), descriptor).check()
            self.assertEqual(error.exception.code, "os_isolation_not_verified")

    def test_02_kernel_message_credentials_refuse_nonroot_writer_even_if_connection_started_root(self):
        sock = framed_peer(reply(), credentials=(22, 1001, 1001))
        with self.assertRaises(Problem):
            transfer(sock, request(), root_only=True)

    def test_03_truncated_missing_or_changed_writer_credentials_refused(self):
        for mode in ("missing", "truncated", "changed"):
            sock = framed_peer(reply())
            original = sock.recvmsg.side_effect
            count = []
            def receive(size, ancsize):
                data, ancillary, flags, address = original(size, ancsize)
                count.append(1)
                if mode == "missing":
                    ancillary = []
                elif mode == "truncated":
                    flags = socket.MSG_CTRUNC
                elif len(count) > 1:
                    ancillary = [(socket.SOL_SOCKET, socket.SCM_CREDENTIALS, struct.pack("3i", 99, 0, 0))]
                return data, ancillary, flags, address
            sock.recvmsg.side_effect = receive
            with self.assertRaises(Problem):
                transfer(sock, request(), root_only=True)

    def test_04_wrong_nonce_context_config_profile_or_denial_refused(self):
        for change in ({"nonce": "e" * 64}, {"context_sha256": "e" * 64}, {"configuration_sha256": "e" * 64},
                       {"profile": "other/v1"}, {"decision": "deny"}, {"verified": True}):
            data = reply()
            data.update(change)
            with self.assertRaises(Problem):
                validate_decision(data, request(), now=100.5)

    def test_05_expired_future_unbounded_boolean_or_nonfinite_lease_refuses(self):
        for change in ({"expires_monotonic": 100}, {"issued_monotonic": 101}, {"expires_monotonic": 103},
                       {"issued_monotonic": False}, {"expires_monotonic": float("nan")}):
            with self.assertRaises(Problem):
                validate_decision({**reply(), **change}, request(), now=100.5)

    def test_06_incomplete_unknown_or_unenforced_guarantee_refuses(self):
        for mode in ("missing", "unknown", "false", "null", "bool_integer"):
            data = reply()
            if mode == "missing":
                del data["guarantees"]["network_ipv6"]
            elif mode == "unknown":
                data["guarantees"]["invented"] = data["guarantees"]["cpu"]
            else:
                data["guarantees"]["cpu"]["enforced"] = {"false": False, "null": None, "bool_integer": 1}[mode]
            with self.assertRaises(Problem):
                validate_decision(data, request(), now=100.5)

    def test_07_unknown_or_worker_evidence_digest_refuses(self):
        for change in ({"policy_sha256": "0" * 64}, {"receipt_sha256": None}, {"policy_sha256": "x" * 64}):
            with self.assertRaises(Problem):
                validate_decision({**reply(), **change}, request(), now=100.5)

    def test_08_valid_synthetic_frame_only_tests_protocol_not_kernel_root_or_os(self):
        result, writer = transfer(framed_peer(reply()), request(), root_only=True)
        self.assertEqual(writer, (12, 0, 0))
        validate_decision(result, request(), now=100.5)

    def test_09_root_controller_refuses_before_using_socket_when_not_privileged(self):
        sock = Mock()
        with patch("os.geteuid", return_value=1001):
            with self.assertRaises(Problem):
                serve_diagnostic(sock, configuration(), {})
        sock.setsockopt.assert_not_called()

    def test_10_controller_uses_message_sender_pid_not_opening_peer(self):
        data, credentials = receive_authenticated_request(framed_peer({"test": 1}, credentials=(42, 1001, 1001)))
        self.assertEqual(credentials, (42, 1001, 1001))
        self.assertEqual(data, {"test": 1})

    def test_11_oversized_frame_or_disconnect_refuse_without_unbounded_read(self):
        for prefix in (0, 131073):
            sock = Mock()
            sock.recv.return_value = struct.pack("!I", prefix)
            with self.assertRaises(Problem):
                transfer(sock)
        sock.recv.return_value = b""
        with self.assertRaises(Problem):
            transfer(sock)

    def test_12_actual_unprivileged_socketpair_exposes_message_credentials_only(self):
        # IPC fixture, no listener/network/privileges or OS-isolation claim.
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        left.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        raw = canonical({"synthetic": True}).encode()
        right.sendall(struct.pack("!I", len(raw)) + raw)
        data, credentials = receive_authenticated_request(left)
        self.assertEqual(credentials, (os.getpid(), os.getuid(), os.getgid()))
        self.assertEqual(data, {"synthetic": True})

    def test_13_received_unexpected_descriptors_are_closed_before_refusal(self):
        import array
        sock = Mock()
        sock.recvmsg.return_value = (b"data", [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [9999]).tobytes())], socket.MSG_CTRUNC, None)
        with patch("os.close") as close:
            with self.assertRaises(Problem):
                transfer(sock, root_only=True)
            close.assert_called_once_with(9999)
        with patch("os.close") as close:
            with self.assertRaises(Problem):
                receive_authenticated_request(sock)
            close.assert_called_once_with(9999)

    def test_14_session_pins_controller_policy_and_process_using_only_mocked_authority(self):
        # All authority syscalls in this test are simulated; not an actual root permit.
        for change in ("policy", "writer", "process"):
            obs = observations()
            obs.update(synthetic=False, unavailable=[])
            obs["process"]["pid"] = 42
            sock = MagicMock()
            sock.__enter__.return_value = sock
            sock.family, sock.type = socket.AF_UNIX, socket.SOCK_STREAM
            sock.getsockopt.return_value = struct.pack("3i", 12, 0, 0)
            calls = []
            def fake_transfer(peer, query, **kwargs):
                data = reply()
                data.update(nonce=query["nonce"], context_sha256=digest(query["context"]))
                writer = (12, 0, 0)
                if calls and change == "policy":
                    data["policy_sha256"] = "e" * 64
                if calls and change == "writer":
                    writer = (13, 0, 0)
                calls.append(1)
                return data, writer
            session = VerificationSession(configuration(), 3, observer=lambda _: deepcopy(obs))
            with patch("os.dup", return_value=9999), patch("os.close"), patch("socket.socket", return_value=sock), \
                 patch("os.getpid", return_value=42), patch("os.getuid", return_value=1001), patch("os.geteuid", return_value=1001), \
                 patch("os.getgid", return_value=1001), patch("os.getegid", return_value=1001), \
                 patch("pepeuch_worker.linux_observer.bounded", return_value="0 0 4294967295"), \
                 patch("pepeuch_worker.verification_channel.transfer", side_effect=fake_transfer), patch("time.monotonic", return_value=100.5):
                session.check()
                if change == "process":
                    obs["process"]["start_ticks"] += 1
                with self.assertRaises(Problem):
                    session.check()

    def test_15_unit_metadata_only_uses_fixed_readonly_command_and_refuses_errors(self):
        import subprocess
        data = b"Id=u.service\nMainPID=42\nControlGroup=/u.service\nInvocationID=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nKillMode=control-group\nRuntimeMaxUSec=55s\nTimeoutStopUSec=5s\n"
        with patch("subprocess.run", return_value=Mock(returncode=0, stdout=data)) as run:
            self.assertEqual(unit_metadata("u.service")["MainPID"], "42")
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ["/usr/bin/systemctl", "show", "--no-pager"])
            self.assertEqual(args[-2:], ["--", "u.service"])
            self.assertEqual(run.call_args.kwargs["timeout"], 1)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("fixed-readonly-command", 1)):
            with self.assertRaises(Problem):
                unit_metadata("u.service")
        with patch("subprocess.run") as run:
            with self.assertRaises(Problem):
                unit_metadata("u.service; unwanted")
            run.assert_not_called()
