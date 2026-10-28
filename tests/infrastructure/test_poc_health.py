"""Read-only inspector: deterministic Docker responses, no daemon required."""

import importlib.util
import json
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[2] / "infrastructure/server/inspect_poc_health.py"
spec = importlib.util.spec_from_file_location("poc_health", path)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class Inventory(unittest.TestCase):
    def run_inventory(self, transform=lambda data: data, listing=None):
        calls = []
        def run(args):
            calls.append(args)
            if args[0] == "ps":
                return "a" * 64 + "\n" if listing is None else listing
            self.assertEqual(args[:3], ["inspect", "--type", "container"])
            index = 0 if "postgres" in calls[-2][-1] and "surrealdb" not in calls[-2][-1] else 1
            project, service, destination, kind = health.SERVICES[index]
            data = {"id": "a" * 64, "image": service + ":synthetic", "state": "running", "health": "healthy", "restart_count": 0,
                    "mounts": [{"type": kind, "destination": destination, "source": "/synthetic/data", "rw": True},
                               {"type": "bind", "destination": "/run/secrets/password", "source": "/private/config", "rw": False}]}
            return json.dumps(transform(data))
        return health.inspect(run), calls

    def test_healthy_proves_only_metadata_and_hides_secret_mounts(self):
        report, calls = self.run_inventory()
        self.assertTrue(all(s["status"] == "VERIFIED" for s in report["services"]))
        self.assertIn("restart_persistence", report["not_verified"])
        self.assertNotIn("/private/config", json.dumps(report))
        self.assertTrue(all(c[0] in {"ps", "inspect"} for c in calls))
        self.assertNotIn(".Config.Env", health.FORMAT)
        self.assertNotIn(".State.Health.Log", health.FORMAT)

    def test_missing_is_unverified_and_never_creates_container(self):
        report, calls = self.run_inventory(listing="")
        self.assertTrue(all(s["status"] == "NOT VERIFIED" for s in report["services"]))
        self.assertEqual(len(calls), 2)

    def test_ambiguous_or_injected_id_never_reaches_inspect(self):
        for listing in ("a" * 64 + "\n" + "b" * 64, "--unexpected-option", "short-id"):
            report, calls = self.run_inventory(listing=listing)
            self.assertTrue(all(s["container"] is None for s in report["services"]))
            self.assertTrue(all(c[0] == "ps" for c in calls))

    def test_stopped_unhealthy_or_no_health_never_reported_verified(self):
        for change in ({"state": "exited"}, {"health": "unhealthy"}, {"health": None}):
            report, _ = self.run_inventory(lambda data: {**data, **change})
            self.assertTrue(all(s["status"] == "PARTIAL" for s in report["services"]))

    def test_missing_wrong_or_read_only_mount_is_partial(self):
        for mounts in ([], [{"type": "tmpfs", "source": "", "destination": "/data", "rw": True}],
                       [{"type": "bind", "source": "/synthetic", "destination": "/data", "rw": False}]):
            report, _ = self.run_inventory(lambda data: {**data, "mounts": mounts})
            self.assertTrue(all(s["status"] == "PARTIAL" for s in report["services"]))

    def test_malformed_or_extra_metadata_never_leaks_payload(self):
        for change in ({"Env": ["private-synthetic-value"]}, {"mounts": "invalid"}, {"restart_count": False}, {"id": "wrong"}):
            report, _ = self.run_inventory(lambda data: {**data, **change})
            self.assertNotIn("private-synthetic-value", json.dumps(report))
            self.assertTrue(all(s["container"] is None for s in report["services"]))

    def test_docker_error_is_redacted_and_other_service_still_checked(self):
        calls = []
        def fail(args):
            calls.append(args)
            raise OSError("synthetic-private-error")
        report = health.inspect(fail)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("synthetic-private-error", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
