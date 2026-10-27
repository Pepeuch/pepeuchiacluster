from copy import deepcopy
import unittest

from control_plane.contracts import Problem
from pepeuch_worker.verification import assess, binding, policy, receipt_errors
from fixtures import configuration, observations, receipt, requested


class Verification(unittest.TestCase):
    def test_01_missing_receipt_and_independent_authority_refuse(self):
        result = assess(configuration(), requested(), observations(), now=101)
        self.assertEqual(result["status"], "NOT VERIFIED")
        self.assertIn("receipt_missing", result["errors"])
        self.assertIn("independent_authority_not_authenticated", result["errors"])
        self.assertFalse(any(p["verified"] for p in result["guarantees"].values()))

    def test_02_worker_reported_root_verified_or_success_never_grants(self):
        for field, value in (("verified", True), ("observer_uid", 0), ("trusted", True), ("synthetic", False)):
            obs = observations()
            obs[field] = value
            result = assess(configuration(), requested(), obs, receipt=receipt(obs), now=101)
            self.assertEqual(result["status"], "NOT VERIFIED")

    def test_03_expired_future_nonfinite_or_boolean_time_refused(self):
        ctx = binding(observations(), requested())
        for change in ({"expires_monotonic": 101}, {"issued_monotonic": 102}, {"expires_monotonic": float("inf")},
                       {"issued_monotonic": False}, {"expires_monotonic": 999}):
            data = receipt()
            data.update(change)
            self.assertTrue(receipt_errors(data, ctx, now=101, max_age=30))

    def test_04_restart_pid_boot_namespace_cgroup_config_and_policy_changes_refuse(self):
        old = receipt()
        for name, value in (("pid", 43), ("start_ticks", 999), ("boot_id", "other"), ("cgroup_inode", 99),
                            ("cgroup", "/other"), ("namespaces", {"user": "other"})):
            obs = observations()
            obs["process"][name] = value
            self.assertTrue(receipt_errors(old, binding(obs, requested()), now=101, max_age=30))
        for name, value in (("profile", "other"), ("invocation_id", "c" * 32), ("configuration_sha256", "c" * 64), ("pids", 4)):
            spec = requested()
            spec[name] = value
            self.assertTrue(receipt_errors(old, binding(observations(), spec), now=101, max_age=30))
        changed_type = deepcopy(old)
        changed_type["binding"]["process"]["status"]["CapEff"] = False
        self.assertTrue(receipt_errors(changed_type, binding(observations(), requested()), now=101, max_age=30))

    def test_05_missing_negative_failed_unknown_method_or_extra_verified_refused(self):
        for change in ("missing", "failed", "method", "invented"):
            data = receipt()
            if change == "missing":
                del data["tests"]["secret"]
            elif change == "failed":
                data["tests"]["secret"]["outcome"] = "fail"
            elif change == "method":
                data["tests"]["secret"]["method"] = "worker-self-report"
            else:
                data["verified"] = True
            self.assertTrue(receipt_errors(data, binding(observations(), requested()), now=101, max_age=30))

    def test_06_missing_controller_unlimited_zero_or_excessive_caps_fail_closed(self):
        for key, value, guarantee in (("controllers", ["cpu"], "cgroup"), ("cpu.max", "max 100000", "cpu"),
            ("cpu.max", "60000 100000", "cpu"), ("cpu.max", "0 100000", "cpu"), ("memory.max", "max", "memory"),
            ("memory.max", "134217729", "memory"), ("pids.max", "9", "pids"), ("memory.swap.max", "max", "swap")):
            obs = observations()
            obs["applied"][key] = value
            self.assertFalse(assess(configuration(), requested(), obs, now=101)["guarantees"][guarantee]["enforced"])

    def test_07_root_groups_no_new_privs_capabilities_and_seccomp_mismatch_refuse(self):
        for name, value, guarantee in (("Uid", [0] * 4, "identity"), ("Groups", [27, 1001], "groups"),
                ("CapBnd", 1, "privileges"), ("CapAmb", 1, "privileges"), ("NoNewPrivs", 0, "privileges"), ("Seccomp", 0, "privileges")):
            obs = observations()
            obs["process"]["status"][name] = value
            self.assertFalse(assess(configuration(), requested(), obs, now=101)["guarantees"][guarantee]["enforced"])

    def test_08_deepest_code_mount_rw_and_stacked_ambiguity_refuse(self):
        for mounts in ([{"mountpoint": "/", "options": ["rw"]}],
                       [{"mountpoint": "/", "options": ["ro"]}, {"mountpoint": "/opt", "options": ["rw"]}],
                       [{"mountpoint": "/", "options": ["ro"]}, {"mountpoint": "/", "options": ["ro"]}]):
            obs = observations()
            obs["applied"]["mounts"] = mounts
            self.assertFalse(assess(configuration(), requested(), obs, now=101)["guarantees"]["code_readonly"]["enforced"])

    def test_09_configuration_mutation_unavailable_or_unstable_observation_refuse(self):
        for change in ({"configuration_sha256": "0" * 64}, {"unavailable": ["pids.max"]}, {"stable": False}):
            obs = observations()
            obs.update(change)
            self.assertTrue(assess(configuration(), requested(), obs, now=101)["errors"])

    def test_10_policy_does_not_accept_unknowns_overlap_root_or_unbounded_limits(self):
        for change in ({"verified": True}, {"worker_root": "/"}, {"code_root": "/var/lib"}, {"memory_bytes": 0},
                       {"pids": True}, {"max_age_seconds": 56}, {"cpu_ratio": float("nan")}, {"allowed_groups": [0]}, {"cgroup": "/../escape"}):
            with self.assertRaises(Problem):
                policy({**requested(), **change})

    def test_11_structurally_valid_fixture_is_only_binding_validation(self):
        self.assertEqual(receipt_errors(receipt(), binding(observations(), requested()), now=101, max_age=30), [])
        result = assess(configuration(), requested(), observations(), receipt=receipt(), now=101)
        self.assertEqual(result["status"], "NOT VERIFIED")
        self.assertIs(result["guarantees"]["cpu"]["enforced"], True)
        self.assertIs(result["guarantees"]["cpu"]["verified"], False)

    def test_12_reports_are_defensive_copies(self):
        data, spec, obs = configuration(), requested(), observations()
        result = assess(data, spec, obs, now=101)
        data["limits"]["seconds"] = 999
        spec["allowed_groups"].append(0)
        obs["process"]["pid"] = 999
        self.assertEqual(result["configuration_requested"]["limits"]["seconds"], 30)
        self.assertEqual(result["policy_requested"]["allowed_groups"], [1001])
        self.assertEqual(result["observations"]["process"]["pid"], 42)

    def test_13_unit_pid_invocation_and_cgroup_must_match_observed_unit(self):
        for value in ("valid", "Id", "MainPID", "InvocationID", "ControlGroup"):
            obs = observations()
            unit = {"Id": requested()["unit"], "MainPID": "42", "InvocationID": requested()["invocation_id"], "ControlGroup": requested()["cgroup"]}
            if value != "valid":
                unit[value] = "different"
            obs["applied"]["systemd"] = unit
            check = assess(configuration(), requested(), obs, now=101)["guarantees"]["unit_binding"]
            self.assertEqual(check["enforced"], value == "valid")
            self.assertFalse(check["verified"])
