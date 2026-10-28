"""Integration on fixtures and temporary private archives; network forbidden."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from discovery_cache import canonical_json
from discovery_checkpoints import load_checkpoint
from discovery_registry import FIXTURE_BINDINGS, discover_fixtures
from execution_models import SourceObservation
from manual_discovery_run import fixture_tasks, run_manual
from test_execution_b44 import FakeClock


NOW = "2026-10-27T12:00:00+00:00"


class ManualRun(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen", "time.sleep"):
            guard = patch(target, side_effect=AssertionError("Offline fixture integration only"))
            guard.start()
            self.addCleanup(guard.stop)
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-manual-run-")
        self.addCleanup(temporary.cleanup)
        self.archive = Path(temporary.name)
        self.tasks = fixture_tasks(tuple(FIXTURE_BINDINGS))
        self.contexts = {t.source: {"domain": "fixtures.invalid", "account_partition": "anonymous", "representation": "metadata-v1"} for t in self.tasks}
        self.events = []

    def run_plan(self, **kwargs):
        defaults = dict(tasks=self.tasks, runtime=FakeClock().runtime(), archive=self.archive, contexts=self.contexts,
                        now=NOW, max_age_seconds=86400, on_event=self.events.append)
        defaults.update(kwargs)
        return run_manual(**defaults)

    def descriptors(self, report):
        return {e["source"]: e["resume"] for e in report["sources"] if e["resume"] is not None}

    def test_all_seven_snapshots_exactly_match_existing_fixture_outputs(self):
        report = self.run_plan()
        self.assertTrue(report["complete"])
        self.assertFalse(report["database_imported"])
        self.assertEqual(report["data_kind"], "synthetic")
        self.assertEqual(len(self.events), 7)
        for source, descriptor in self.descriptors(report).items():
            cached = load_checkpoint(self.archive, descriptor["request"], descriptor["identity"])
            self.assertEqual(canonical_json(cached["snapshot"]), canonical_json(discover_fixtures(sources=[source])))
            self.assertEqual(cached["provenance"]["kind"], "synthetic")

    def test_restart_uses_explicit_generations_without_calling_operations_or_refreshing_dates(self):
        first = self.run_plan()
        before = {p.name: p.read_bytes() for p in self.archive.glob("*.json")}
        def forbidden(ctx):
            raise AssertionError("Fresh archive must not call operations")
        second = self.run_plan(tasks=[replace(t, operation=forbidden) for t in self.tasks], resume=self.descriptors(first))
        self.assertTrue(all(e["status"] == "resumed_cached" for e in second["sources"]))
        self.assertTrue(all(e["remote_revalidated"] is False for e in second["sources"]))
        self.assertEqual([e["captured_at"] for e in first["sources"]], [e["captured_at"] for e in second["sources"]])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.archive.glob("*.json")})

    def test_partial_source_is_not_archived_and_other_sources_survive(self):
        task = self.tasks[1]
        incomplete = discover_fixtures(sources=[task.source])
        bad = replace(task, operation=lambda ctx: SourceObservation(incomplete, False))
        report = self.run_plan(tasks=[self.tasks[0], bad, *self.tasks[2:]])
        self.assertFalse(report["complete"])
        self.assertEqual(report["requested_sources"], list(FIXTURE_BINDINGS))
        self.assertEqual(report["sources"][1]["execution"]["reason"], "selection_incomplete")
        self.assertIsNone(report["sources"][1]["resume"])
        self.assertEqual(len(list(self.archive.glob("*.json"))), 6)

    def test_interruption_after_publication_preserves_a_resumable_source(self):
        published = []
        def stop(event):
            published.append(event)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_plan(on_event=stop)
        self.assertEqual(len(list(self.archive.glob("*.json"))), 1)
        resume = {published[0]["source"]: published[0]["resume"]}
        report = self.run_plan(resume=resume)
        self.assertEqual(report["sources"][0]["status"], "resumed_cached")
        self.assertEqual(len(list(self.archive.glob("*.json"))), 7)

    def test_stale_cache_executes_again_and_preserves_original_generation(self):
        first = self.run_plan()
        second = self.run_plan(resume=self.descriptors(first), max_age_seconds=0)
        self.assertTrue(all(e["status"] == "success" for e in second["sources"]))
        self.assertEqual(self.descriptors(first), self.descriptors(second))

    def test_two_captures_keep_same_b2_id_but_distinct_immutable_archives(self):
        first = self.run_plan()
        def changed_date(ctx, source):
            return SourceObservation(discover_fixtures(sources=[source], captured_at="2026-10-27T11:00:00+00:00"), True)
        tasks = [replace(t, operation=lambda ctx, source=t.source: changed_date(ctx, source)) for t in self.tasks]
        second = self.run_plan(tasks=tasks, max_age_seconds=0)
        self.assertEqual([e["snapshot_id"] for e in first["sources"]], [e["snapshot_id"] for e in second["sources"]])
        self.assertEqual(len(list(self.archive.glob("*.json"))), 14)
        self.assertNotEqual(self.descriptors(first), self.descriptors(second))

    def test_corrupt_resume_is_refused_before_any_execution_and_preserved(self):
        first = self.run_plan()
        resume = self.descriptors(first)
        path = self.archive / (resume[self.tasks[-1].source]["identity"] + ".json")
        path.write_bytes(b"corrupt generation preserved")
        self.events.clear()
        with self.assertRaises(ValueError):
            self.run_plan(resume=resume)
        self.assertEqual(self.events, [])
        self.assertEqual(path.read_bytes(), b"corrupt generation preserved")

    def test_partition_change_refused_without_cross_account_reuse(self):
        resume = self.descriptors(self.run_plan())
        for field in self.contexts[self.tasks[0].source]:
            contexts = deepcopy(self.contexts)
            contexts[self.tasks[0].source][field] = "another-public-partition"
            with self.assertRaises(ValueError):
                self.run_plan(resume=resume, contexts=contexts)

    def test_unauthorized_resource_cannot_bypass_execution_by_resume(self):
        first = self.run_plan()
        task = self.tasks[0]
        other = self.tasks[1].resources[0]
        tasks = [replace(task, policy=replace(task.policy, resources=frozenset({other}))), *self.tasks[1:]]
        with self.assertRaises(ValueError):
            self.run_plan(tasks=tasks, resume=self.descriptors(first))

    def test_explicit_null_resume_descriptor_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            self.run_plan(resume={self.tasks[0].source: None})
        self.assertEqual(self.events, [])
        self.assertEqual(list(self.archive.glob("*.json")), [])

    def test_future_observations_invalid_time_and_unbounded_age_refused(self):
        for params in ({"now": "2026-10-26T00:00:00+00:00"}, {"now": "2026-10-27T12:00:00"},
                       {"max_age_seconds": float("nan")}, {"max_age_seconds": True}, {"max_age_seconds": 604801}):
            with self.assertRaises(ValueError):
                self.run_plan(**params)
        self.assertEqual(list(self.archive.glob("*.json")), [])

    def test_controlled_operation_requires_enrolled_issuer_before_execution(self):
        task = self.tasks[1]
        calls = []
        controlled = replace(task, synthetic=False, operation=lambda ctx: calls.append(True))
        with self.assertRaises(ValueError):
            self.run_plan(tasks=[controlled], contexts={task.source: self.contexts[task.source]})
        self.assertEqual(calls, [])

    def test_observer_cannot_mutate_returned_resume_or_archive(self):
        def mutate(event):
            event["resume"]["request"]["context"]["domain"] = "mutated.invalid"
        report = self.run_plan(on_event=mutate)
        self.assertTrue(all(e["resume"]["request"]["context"]["domain"] == "fixtures.invalid" for e in report["sources"]))


if __name__ == "__main__":
    unittest.main()
