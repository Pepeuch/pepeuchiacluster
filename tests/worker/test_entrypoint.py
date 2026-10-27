import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from control_plane.contracts import canonical
from test_contracts import config


class Entrypoint(unittest.TestCase):
    def test_new_cli_initialization_inspection_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b53-cli-") as temporary:
            root = Path(temporary)
            path = root / "public-config.json"
            path.write_text(canonical(config()))
            args = [sys.executable, "-m", "pepeuch_worker", "init", "--worker-dir", str(root / "worker"), "--configuration-file", str(path)]
            first = subprocess.run(args, capture_output=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = (root / "worker/worker.json").read_bytes()
            repeated = subprocess.run(args, capture_output=True, timeout=10)
            self.assertEqual(repeated.returncode, 1)
            self.assertEqual((root / "worker/worker.json").read_bytes(), before)
            report = subprocess.run([sys.executable, "-m", "pepeuch_worker", "inspect", "--worker-dir", str(root / "worker")], capture_output=True, timeout=10)
            self.assertEqual(json.loads(report.stdout)["status"], "NOT VERIFIED")

    def test_entrypoint_imports_no_backend_database_sdk_or_process_executor(self):
        # A fresh interpreter avoids inheriting imports made by the test harness.
        program = r'''
import importlib.abc, runpy, sys
blocked = {"sqlite3", "subprocess", "torch", "requests", "control_plane.storage", "control_plane.service", "control_plane.auth", "control_plane.http_api", "control_plane.workspace", "control_plane.worker_registry"}
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("forbidden import")
sys.meta_path.insert(0, Guard())
sys.argv = ["pepeuch_worker", "--help"]
runpy.run_module("pepeuch_worker", run_name="__main__")
'''
        result = subprocess.run([sys.executable, "-c", program], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"--data-dir", result.stdout)
        self.assertNotIn(b"--credential ", result.stdout)

    def test_strict_failure_logs_neither_configuration_objective_nor_exception_paths(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b53-error-") as temporary:
            root = Path(temporary)
            marker = "sensitive-synthetic-value"
            path = root / "config.json"
            path.write_text(canonical({**config(), "credential": marker}))
            result = subprocess.run([sys.executable, "-m", "pepeuch_worker", "init", "--worker-dir", str(root / "worker"),
                                     "--configuration-file", str(path)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(marker.encode(), result.stdout + result.stderr)
            self.assertNotIn(str(root).encode(), result.stdout + result.stderr)
            self.assertFalse((root / "worker").exists())
