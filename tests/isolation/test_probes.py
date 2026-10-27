import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from control_plane.contracts import Problem
from pilot.worker_isolation.__main__ import prepare, protected_scope
from pilot.worker_isolation.probes import connect, deny_open, device_metadata, scope, require_lifecycle_limits


def pilot_scope():
    return {"schema": "pepeuch.worker/isolation-pilot/v1", "run_id": "a" * 32,
            "fixture_root": "/opt/pepeuch-b531-fixtures-" + "a" * 32, "backend_port": 8765,
            "blocked_loopback_port": 8766, "peer_ipv4": "192.168.99.2", "peer_ipv6": "fd00::2", "peer_port": 8767,
            "expected_uid": 1001, "expected_gid": 1001, "boot_id": "11111111-1111-1111-1111-111111111111",
            "created_monotonic": 100, "expires_monotonic": 200}


class FixedProbes(unittest.TestCase):
    def test_01_real_paths_internet_root_shared_port_or_unknown_tool_refused(self):
        for change in ({"fixture_root": "/var/lib/real-backend"}, {"peer_ipv4": "8.8.8.8"}, {"peer_ipv6": "2001:4860:4860::8888"},
                       {"peer_ipv4": "localhost"}, {"expected_uid": 0}, {"backend_port": True}, {"blocked_loopback_port": 8765}, {"command": "anything"}):
            with self.assertRaises(Problem):
                scope({**pilot_scope(), **change})

    def test_02_prepare_nonroot_refuses_before_creating_any_fixture(self):
        with patch("os.geteuid", return_value=1001), patch("os.mkdir") as mkdir:
            with self.assertRaises(Problem):
                prepare(pilot_scope())
            mkdir.assert_not_called()

    def test_03_scope_path_outside_fixed_canary_tree_refuses_before_open(self):
        with patch("os.open") as open_:
            with self.assertRaises(Problem):
                protected_scope(Path("/secrets/admin.token"))
            open_.assert_not_called()

    def test_04_missing_file_not_a_denial(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b531-probe-fixture-") as temporary:
            result = deny_open(Path(temporary) / "absent")
        self.assertEqual(result["outcome"], "NOT VERIFIED")
        self.assertEqual(result["errno"], errno.ENOENT)

    def test_05_unexpected_read_or_write_neither_reads_nor_mutates_bytes(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b531-probe-fixture-") as temporary:
            path = Path(temporary) / "synthetic-canary"
            path.write_bytes(b"synthetic preserved bytes")
            for writing in (False, True):
                result = deny_open(path, writing=writing)
                self.assertEqual(result["outcome"], "FAIL")
                self.assertEqual(path.read_bytes(), b"synthetic preserved bytes")

    def test_06_only_permission_and_readonly_errnos_are_candidate_denials(self):
        for code, expected in ((errno.EACCES, "candidate_denial"), (errno.EPERM, "candidate_denial"),
                               (errno.ENOENT, "NOT VERIFIED"), (errno.EIO, "NOT VERIFIED")):
            with patch("os.open", side_effect=OSError(code, "synthetic error text never emitted")):
                self.assertEqual(deny_open(Path("/synthetic/canary"))["outcome"], expected)

    def test_07_refused_connection_and_timeout_never_count_as_filter(self):
        for error in (ConnectionRefusedError(errno.ECONNREFUSED, "synthetic"), TimeoutError()):
            sock = Mock()
            sock.__enter__ = Mock(return_value=sock)
            sock.__exit__ = Mock(return_value=False)
            sock.connect.side_effect = error
            with patch("socket.socket", return_value=sock):
                self.assertEqual(connect(pilot_scope(), "other_loopback")["outcome"], "NOT VERIFIED")

    def test_08_private_peer_only_connect_without_sending_bytes(self):
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        with patch("socket.socket", return_value=sock):
            self.assertEqual(connect(pilot_scope(), "backend_connect")["outcome"], "candidate_reachable")
        sock.connect.assert_called_once_with(("127.0.0.1", 8765))
        sock.send.assert_not_called()
        sock.sendall.assert_not_called()
        sock.settimeout.assert_called_once_with(0.3)

    def test_09_network_permission_denial_is_not_self_authenticated_proof(self):
        with patch("socket.socket", side_effect=PermissionError(errno.EACCES, "synthetic")):
            result = connect(pilot_scope(), "ipv6")
        self.assertEqual(result["outcome"], "candidate_denial")
        self.assertNotIn("verified", result)

    def test_10_device_probe_only_stats_no_gpu_or_docker_open(self):
        with patch("os.lstat", side_effect=FileNotFoundError(errno.ENOENT, "synthetic")), patch("os.open") as open_, patch("socket.socket") as socket_:
            self.assertEqual(device_metadata()["outcome"], "NOT VERIFIED")
        open_.assert_not_called()
        socket_.assert_not_called()

    def test_11_lifecycle_probes_refuse_missing_unlimited_or_privileged_environment(self):
        from fixtures import observations
        for field, value in (("pids.max", "max"), ("memory.max", "max"), ("cpu.max", "max 100000"), ("memory.swap.max", "1")):
            obs = observations()
            obs["applied"][field] = value
            with self.assertRaises(Problem):
                require_lifecycle_limits(obs)
        obs = observations()
        obs["process"]["status"]["NoNewPrivs"] = 0
        with self.assertRaises(Problem):
            require_lifecycle_limits(obs)

    def test_12_bounded_fixture_lifecycle_preflight_is_only_numeric_validation(self):
        from fixtures import observations
        require_lifecycle_limits(observations())

    def test_13_preparation_refuses_existing_before_fully_mocked_root_success(self):
        # Every filesystem operation and root identity below is simulated.
        import os
        manager = MagicMock()
        manager.__enter__.return_value = 99
        with patch("os.geteuid", return_value=0), patch("pilot.worker_isolation.__main__.opened_directory", return_value=manager), \
             patch("os.mkdir", side_effect=FileExistsError), patch("os.open") as open_:
            with self.assertRaises(FileExistsError):
                prepare(pilot_scope())
            open_.assert_not_called()
        with patch("os.geteuid", return_value=0), patch("pilot.worker_isolation.__main__.opened_directory", return_value=manager), \
             patch("os.mkdir") as mkdir, patch("pathlib.Path.mkdir"), patch("os.open", return_value=88) as open_, \
             patch("os.write"), patch("os.fchmod") as chmod, patch("os.fsync"), patch("os.close"):
            prepare(pilot_scope())
            self.assertEqual(mkdir.call_args.args[0], "pepeuch-b531-fixtures-" + "a" * 32)
            for call in open_.call_args_list:
                self.assertTrue(str(call.args[0]).startswith(pilot_scope()["fixture_root"] + "/"))
                self.assertTrue(call.args[1] & os.O_EXCL)
                self.assertTrue(call.args[1] & os.O_NOFOLLOW)
            self.assertIn(unittest.mock.call(88, 0o666), chmod.call_args_list)
            self.assertIn(unittest.mock.call(88, 0o444), chmod.call_args_list)
