import hashlib
import json
import threading
import unittest
from unittest.mock import patch

from control_plane.contracts import Problem, sha256
from control_plane.demo import FakeWorker
from control_plane.worker_client import validate_request
from pepeuch_worker.executor import CPUTextDigest
from support import content, request
from test_contracts import config


class Executor(unittest.TestCase):
    def executor(self, **kwargs):
        return CPUTextDigest(config()["limits"], **kwargs)

    def test_deterministic_utf8_digest_not_a_shell_or_inference(self):
        data = request()
        with patch("builtins.open", side_effect=AssertionError("no filesystem")), patch("socket.socket", side_effect=AssertionError("no network")):
            first = self.executor().execute(data)
            second = self.executor().execute(data)
        self.assertEqual(first, second)
        raw = content(first)
        report = json.loads(raw.decode().split("```json\n")[1].split("\n```")[0])
        self.assertEqual(report["input_sha256"], hashlib.sha256(data["mission"]["objective"].encode()).hexdigest())
        self.assertEqual(report["input_bytes"], len(data["mission"]["objective"].encode()))
        self.assertIs(report["ai_inference"], False)
        self.assertEqual(first.outputs[0]["sha256"], sha256(raw))
        self.assertNotIn(data["mission"]["objective"].encode(), raw)

    def test_historical_worker_and_default_validator_refuse_cpu(self):
        for callable_ in (FakeWorker().execute, validate_request):
            with self.assertRaises(Problem):
                callable_(request())

    def test_unknown_capability_tool_paths_and_file_inputs_refused(self):
        for change in ("capability", "tool", "path", "authorized_files", "role", "simulated"):
            data = request()
            if change == "capability":
                data["task"]["capability"] = "shell.exec.v1"
            elif change in ("tool", "path"):
                data[change] = "../../outside"
            elif change == "role":
                data["task"]["role"] = "shell"
            elif change == "simulated":
                data["task"]["simulated"] = True
            else:
                data[change] = ["v_" + "0" * 32]
            with self.assertRaises(Problem):
                self.executor().execute(data)

    def test_input_output_limits_are_application_bounds(self):
        for name in ("input_bytes", "output_bytes"):
            limits = config()["limits"]
            limits[name] = 1
            with self.assertRaises(Problem):
                CPUTextDigest(limits).execute(request())

    def test_deadline_before_and_during_hash(self):
        data = request()
        expired = self.executor(wall=lambda: data["deadline"]).execute(data)
        self.assertEqual(expired.error_code, "cpu_deadline_exceeded")
        data["mission"]["objective"] = "a" * 3000
        times = iter((0, 0, 31))
        during = self.executor(wall=lambda: 0, monotonic=lambda: next(times)).execute(data)
        self.assertEqual(during.status, "interrupted")
        self.assertEqual(during.error_code, "cpu_deadline_exceeded")

    def test_cooperative_stop_during_calculation(self):
        stop = threading.Event()
        data = request()
        data["mission"]["objective"] = "b" * 3000
        calls = []
        def wall():
            calls.append(1)
            if len(calls) == 2:
                stop.set()
            return 0
        result = self.executor(stop=stop, wall=wall).execute(data)
        self.assertEqual(result.status, "interrupted")
        self.assertEqual(result.error_code, "cpu_interrupted")
        self.assertEqual(result.outputs, [])

    def test_cancel_produces_no_output(self):
        result = self.executor().execute(request(), mode="cancel")
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.outputs, [])

    def test_limits_are_copied_and_strict(self):
        limits = config()["limits"]
        executor = CPUTextDigest(limits)
        limits["output_bytes"] = 1
        self.assertEqual(executor.execute(request()).status, "completed")
        for change in ({"tasks": 2}, {"seconds": False}, {"command": "x"}):
            with self.assertRaises(Problem):
                CPUTextDigest({**config()["limits"], **change})
