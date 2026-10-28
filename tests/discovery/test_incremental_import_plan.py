"""Import protocol simulations; NOT verification of PostgreSQL/SurrealDB behavior."""

from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from discovery_cache import make_snapshot
from discovery_provenance import make_provenance
from discovery_registry import discover_fixtures
from incremental_import_plan import plan_import
from source_adapters import SourceRecord
from validated_discovery_cache import cache_request, make_cache


def entry(snapshot):
    source = next(iter(snapshot["scope"]))
    context = {"domain": "fixtures.invalid", "account_partition": "anonymous", "representation": "metadata-v1"}
    request = cache_request(source, snapshot["scope"][source], [r["source_id"] for r in snapshot["records"]], context=context,
                            revisions={r["source_id"]: r["source_revision"] for r in snapshot["records"]})
    return make_cache(request, snapshot, make_provenance(snapshot, kind="synthetic", context=context),
                      validators={"etag": None, "last_modified": None})


def simulate_protocol(state, plan, *, atomic, fail_after=None):
    """Oracle for proposed preconditions, not an engine adapter or SQL parser."""
    staged = deepcopy(state)
    for index, action in enumerate(plan["actions"]):
        if index == fail_after:
            raise InterruptedError("injected protocol failure")
        record, expected = action["record"], action["expected"]
        existing = staged.get(record["record_key"])
        if existing != record:
            if (expected is None and existing is not None or expected is not None
                    and (existing is None or {k: existing[k] for k in expected} != expected)):
                raise ValueError("Concurrent or stale replacement refused")
            staged[record["record_key"]] = deepcopy(record)
        if not atomic:
            state.update(deepcopy(staged))
    if atomic:
        state.update(staged)


class IncrementalPlan(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("No real database or transport"))
            guard.start()
            self.addCleanup(guard.stop)
        snapshot = discover_fixtures(sources=["models.dev"])
        records = []
        for item in snapshot["records"]:
            record = SourceRecord(**{k: deepcopy(v) for k, v in item.items() if k not in {"record_key", "payload_sha256"}})
            records.append(record)
        # Dedicated synthetic second row exercises failure after a committed
        # prefix. Do not alter historical one-row fixtures or their references.
        records.append(replace(records[0], source_id="synthetic/second-reference", display_name="Synthetic second reference"))
        scope = {"models.dev": {"mode": "first_n_sorted", "limit": 2}}
        self.before = entry(make_snapshot(records, scope=scope, captured_at=snapshot["captured_at"]))
        changed = [replace(record, source_revision="synthetic-next-revision") for record in records]
        self.after = entry(make_snapshot(changed, scope=scope, captured_at="2026-10-28T00:00:00+00:00"))

    def test_initial_import_requires_absence_and_never_becomes_executable(self):
        plan = plan_import(None, self.before)
        self.assertFalse(plan["executable"])
        self.assertFalse(plan["legacy_generators_guarded"])
        self.assertEqual(plan["delete_actions"], [])
        self.assertTrue(all(a["expected"] is None for a in plan["actions"]))

    def test_revision_changes_keep_identities_and_plan_only_upserts(self):
        plan = plan_import(self.before, self.after)
        self.assertEqual([r["record_key"] for r in self.before["snapshot"]["records"]], [a["record"]["record_key"] for a in plan["actions"]])
        self.assertEqual(len(plan["changes"]["changed"]), len(plan["actions"]))
        self.assertEqual(plan["delete_actions"], [])

    def test_older_or_conflicting_capture_is_refused(self):
        with self.assertRaises(ValueError):
            plan_import(self.after, self.before)
        conflict = deepcopy(self.after["snapshot"])
        conflict["captured_at"] = self.before["snapshot"]["captured_at"]
        with self.assertRaises(ValueError):
            plan_import(self.before, entry(conflict))

    def test_atomic_failure_keeps_baseline_then_replay_succeeds(self):
        state = {}
        simulate_protocol(state, plan_import(None, self.before), atomic=True)
        original = deepcopy(state)
        plan = plan_import(self.before, self.after)
        with self.assertRaises(InterruptedError):
            simulate_protocol(state, plan, atomic=True, fail_after=1)
        self.assertEqual(state, original)
        simulate_protocol(state, plan, atomic=True)
        simulate_protocol(state, plan, atomic=True)
        self.assertEqual({r["last_seen_snapshot"] for r in state.values()}, {self.after["snapshot"]["snapshot_id"]})

    def test_statement_prefix_failure_replays_idempotently_and_keeps_unobserved_record(self):
        state = {"unobserved": {"opaque": "preserve"}}
        simulate_protocol(state, plan_import(None, self.before), atomic=False)
        plan = plan_import(self.before, self.after)
        with self.assertRaises(InterruptedError):
            simulate_protocol(state, plan, atomic=False, fail_after=1)
        self.assertEqual(state[plan["actions"][0]["record"]["record_key"]], plan["actions"][0]["record"])
        simulate_protocol(state, plan, atomic=False)
        simulate_protocol(state, plan, atomic=False)
        self.assertEqual(state["unobserved"], {"opaque": "preserve"})

    def test_simultaneous_newer_state_is_never_overwritten_by_proposed_protocol(self):
        state = {}
        simulate_protocol(state, plan_import(None, self.before), atomic=True)
        first_key = self.before["snapshot"]["records"][0]["record_key"]
        state[first_key]["last_seen_at"] = "2026-10-29T00:00:00+00:00"
        original = deepcopy(state)
        with self.assertRaises(ValueError):
            simulate_protocol(state, plan_import(self.before, self.after), atomic=True)
        self.assertEqual(state, original)

    def test_changed_scope_partition_or_origin_refused(self):
        for field in ("domain", "account_partition", "representation"):
            changed = deepcopy(self.after)
            changed["request"]["context"][field] = "different-public-partition"
            changed["provenance"]["context"][field] = "different-public-partition"
            with self.assertRaises(ValueError):
                plan_import(self.before, changed)
        other = entry(discover_fixtures(sources=["huggingface"]))
        with self.assertRaises(ValueError):
            plan_import(self.before, other)

    def test_plan_and_oracle_do_not_mutate_cache_snapshots(self):
        before, after = deepcopy(self.before), deepcopy(self.after)
        plan = plan_import(self.before, self.after)
        plan["actions"][0]["record"]["attributes"]["external_mutation"] = True
        self.assertEqual(self.before, before)
        self.assertEqual(self.after, after)

    def test_not_observed_resource_is_reported_without_any_delete_or_replacement(self):
        snapshot = self.after["snapshot"]
        first = snapshot["records"][0]
        record = SourceRecord(**{k: deepcopy(v) for k, v in first.items() if k not in {"record_key", "payload_sha256"}})
        reduced = entry(make_snapshot([record], scope=snapshot["scope"], captured_at=snapshot["captured_at"]))
        plan = plan_import(self.before, reduced)
        missing = self.before["snapshot"]["records"][1]["record_key"]
        self.assertEqual(plan["changes"]["not_observed"], [missing])
        self.assertEqual(plan["delete_actions"], [])
        self.assertNotIn(missing, [a["record"]["record_key"] for a in plan["actions"]])


if __name__ == "__main__":
    unittest.main()
