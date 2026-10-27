from copy import deepcopy
import unittest

from control_plane.contracts import Problem
from pepeuch_worker.contracts import CONFIG_SCHEMA, CPU_PROFILE, SecurityProperty, configuration, require_verified


def config():
    return {"schema": CONFIG_SCHEMA, "worker_id": "n_" + "1" * 32, "backend_url": "http://127.0.0.1:8765",
            "capabilities": ["cpu.text.sha256.v1"], "tools": [],
            "limits": {"input_bytes": 16000, "output_bytes": 65536, "seconds": 30, "tasks": 1},
            "os_profile": {"schema": CPU_PROFILE, "expected_uid": 1001, "expected_gid": 1001, "backend_uid": 1000}}


class Contracts(unittest.TestCase):
    def test_closed_configuration_separates_cluster_identity_and_os_identity(self):
        data = configuration(config())
        self.assertEqual(data["worker_id"], "n_" + "1" * 32)
        self.assertEqual(data["os_profile"]["expected_uid"], 1001)
        self.assertNotIn("credential", data)

    def test_no_shell_tools_inference_or_gpu_capability(self):
        for capabilities, tools in ((["shell"], []), (["gpu"], []), (["cpu.text.sha256.v1"], ["exec"])):
            data = config()
            data.update(capabilities=capabilities, tools=tools)
            with self.assertRaises(Problem):
                configuration(data)

    def test_endpoints_are_loopback_only_without_credentials(self):
        for endpoint in ("https://provider.test", "http://user@127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:8765?key=x",
                         "http://127.0.0.1:8765\n", "http://127.0.0.1:8765/#", "http://127.0.0.1:0", "http://127.0.0.1:65536"):
            data = config()
            data["backend_url"] = endpoint
            with self.assertRaises(Problem):
                configuration(data)

    def test_unknown_or_invented_security_fields_are_refused(self):
        data = config()
        data["os_profile"]["verified"] = True
        with self.assertRaises(Problem):
            configuration(data)

    def test_bounds_reject_unknown_false_and_excessive_values(self):
        for name, value in (("tasks", 2), ("input_bytes", 16001), ("seconds", False), ("output_bytes", None)):
            data = deepcopy(config())
            data["limits"][name] = value
            with self.assertRaises(Problem):
                configuration(data)

    def test_declaration_is_not_enforcement_or_verification(self):
        declared = SecurityProperty("separate_uid", None, False, "NOT VERIFIED")
        with self.assertRaises(Problem):
            require_verified({"uid": declared})
        with self.assertRaises(Problem):
            SecurityProperty("separate_uid", False, True, "invalid claim")
        with self.assertRaises(Problem):
            require_verified({"uid": {"verified": True, "enforced": True}})
