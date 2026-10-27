import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from control_plane.contracts import canonical
from fixtures import configuration, requested


class VerifierCLI(unittest.TestCase):
    def test_01_controller_without_authorization_refuses_before_paths_or_socket(self):
        result = subprocess.run([sys.executable, "-m", "pilot.worker_isolation.controller", "--run-id", "a" * 32,
                                 "--configuration-file", "/not-opened", "--policy-file", "/not-opened"], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"NOT VERIFIED", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_02_probes_require_explicit_pilot_before_reading_scope(self):
        result = subprocess.run([sys.executable, "-m", "pilot.worker_isolation", "probe", "--scope-file", "/not-opened", "--case", "controlled_peer"],
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"NOT VERIFIED", result.stderr)

    def test_03_readonly_audit_is_not_launch_permission(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b531-audit-cli-") as temporary:
            root = Path(temporary)
            (root / "config.json").write_text(canonical(configuration()))
            (root / "policy.json").write_text(canonical(requested()))
            result = subprocess.run([sys.executable, "-m", "pepeuch_worker.verifier", "--configuration-file", str(root / "config.json"),
                                     "--policy-file", str(root / "policy.json")], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "NOT VERIFIED")
            self.assertIn("independent_authority_not_authenticated", report["errors"])
            self.assertFalse(any(item["verified"] for item in report["guarantees"].values()))

    def test_04_privileged_verifier_mode_without_authorization_does_no_io(self):
        result = subprocess.run([sys.executable, "-m", "pepeuch_worker.verifier", "--configuration-file", "/not-opened",
                                 "--policy-file", "/not-opened", "--serve-fd", "3"], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"NOT VERIFIED", result.stderr)
