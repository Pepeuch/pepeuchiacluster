from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from control_plane.contracts import Problem, new_id
from pepeuch_worker import private_io
from pepeuch_worker.executor import CPUTextDigest
from pepeuch_worker.runner import IndependentRunner
from fixtures import configuration


def task_request():
    mission = new_id("m")
    return {"schema": "pepeuch.control-plane/execution-request/v1", "attempt_id": new_id("a"), "generation": new_id("g"),
            "task": {"schema": "pepeuch.control-plane/task/v1", "id": new_id("t"), "mission_id": mission,
                     "role": "cpu-text-digest", "capability": "cpu.text.sha256.v1", "worker_id": configuration()["worker_id"],
                     "state": "running", "simulated": False},
            "mission": {"id": mission, "title": "Synthétique", "objective": "Hash CPU sans shell"}, "authorized_files": [],
            "started_at": "2026-10-27T00:00:00+00:00", "deadline": time.time() + 60, "expected_version": None}


class RunnerGuard(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b531-guard-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.request = task_request()
        self.client = Mock()
        def call(method, path, data=None):
            if path.endswith("/claim"):
                return {"request": deepcopy(self.request)}
            if path.endswith("/state"):
                return {"schema": "pepeuch.control-plane/attempt-state/v1", "state": "running", "deadline": self.request["deadline"]}
            return {"accepted": True, "duplicate": False, "mission_id": self.request["mission"]["id"]}
        self.client.call.side_effect = call

    def runner(self, guard, executor=None):
        return IndependentRunner(self.root, configuration(), "x" * 43, self.client,
                                 CPUTextDigest(configuration()["limits"]) if executor is None else executor,
                                 isolation_guard=guard)

    def test_01_guard_denies_before_claim_or_journal_creation(self):
        with self.assertRaises(Problem):
            self.runner(Mock(side_effect=Problem("os_isolation_not_verified"))).run_once()
        self.client.call.assert_not_called()
        self.assertIsNone(private_io.load(self.root))

    def test_02_revoked_proof_prevents_execution(self):
        guard = Mock(side_effect=[None, Problem("os_isolation_not_verified")])
        executor = Mock()
        with self.assertRaises(Problem):
            self.runner(guard, executor).run_once()
        executor.execute.assert_not_called()
        self.assertFalse(private_io.load(self.root)["done"])
        self.assertIsNone(private_io.load(self.root)["result"])

    def test_03_changed_proof_blocks_finish_preserving_durable_result(self):
        guard = Mock(side_effect=[None, None, Problem("os_isolation_not_verified")])
        with self.assertRaises(Problem):
            self.runner(guard).run_once()
        journal = private_io.load(self.root)
        self.assertEqual(journal["result"]["status"], "completed")
        self.assertFalse(journal["done"])
        self.assertFalse(any(call.args[1].endswith("/finish") for call in self.client.call.call_args_list))

    def test_04_recovery_also_requires_fresh_proof(self):
        with self.assertRaises(Problem):
            self.runner(Mock(side_effect=[None, None, Problem("os_isolation_not_verified")])).run_once()
        before = private_io.load(self.root)
        with self.assertRaises(Problem):
            self.runner(Mock(side_effect=Problem("os_isolation_not_verified"))).run_once(recover=True)
        self.assertEqual(private_io.load(self.root), before)

    def test_05_synthetic_guard_success_preserves_application_protocol(self):
        guard = Mock()
        self.assertEqual(self.runner(guard).run_once(), "completed")
        self.assertEqual(guard.call_count, 3)
        self.assertTrue(private_io.load(self.root)["done"])
