"""B4.4: simulated clocks/transports only; no network, real sleep or DB."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from http.client import IncompleteRead
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from discovery_cache import make_snapshot
from discovery_execution import classify_error, execute_source, execute_sources
from discovery_registry import discover_fixtures
from execution_models import (
    ExecutionError, ExecutionPolicy, ExecutionReport, ExecutionRuntime, Reason,
    ResourceRef, SourceObservation, SourceResult, SourceTask, Status,
)
from metadata_http import HTTPPolicy, HTTPResult, MetadataHTTPError, MetadataResponseError, get_metadata_json
from retry_after import RetryAfter, parse_retry_after
from source_adapters import SourceRecord, normalize_huggingface_model


ROOT = Path(__file__).resolve().parent


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.epoch = datetime(2026, 10, 27, 12, tzinfo=timezone.utc).timestamp()
        self.waits = []
        self.jitter_inputs = []
        self.added_jitter = 0.0

    def sleep(self, delay):
        self.waits.append(delay)
        self.now += delay

    def jitter(self, base):
        self.jitter_inputs.append(base)
        return self.added_jitter

    def runtime(self):
        return ExecutionRuntime(lambda: self.now, lambda: self.epoch + self.now, self.sleep, self.jitter)


class ExecutionB44Tests(unittest.TestCase):
    def setUp(self):
        for target in ("time.sleep", "socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("Real wait/network/subprocess forbidden in B4.4"))
            guard.start()
            self.addCleanup(guard.stop)
        self.clock = FakeClock()

    def task(self, source="huggingface", actions=None, **limits):
        snapshot = discover_fixtures(sources=[source])
        refs = tuple(ResourceRef(source, r["source_id"]) for r in snapshot["records"])
        values = dict(max_requests=5, max_attempts=5, total_seconds=30, max_delay_seconds=10,
                      backoff_seconds=1, resources=frozenset(refs),
                      retry_http_statuses=frozenset({429, 500, 502, 503, 504}), retry_transport_errors=True)
        values.update(limits)
        observation = SourceObservation(snapshot, True)
        iterator = iter([observation] if actions is None else actions)
        calls = []
        def operation(context):
            def request(remaining):
                calls.append(remaining)
                action = next(iterator)
                if isinstance(action, Exception):
                    raise action
                if callable(action):
                    return action(remaining)
                return observation if action == "success" else action
            return context.request(refs[0], request)
        return SourceTask(source, snapshot["scope"][source], refs, ExecutionPolicy(**values), operation, True, True), calls, observation

    def run_task(self, task, runtime=None):
        return execute_source(task, runtime=self.clock.runtime() if runtime is None else runtime)

    def test_immediate_success_references_exact_valid_snapshot(self):
        task, calls, expected = self.task()
        result = self.run_task(task)
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(result.snapshot, expected.snapshot)
        self.assertEqual((result.attempts, result.requests), (1, 1))
        self.assertEqual(calls, [30])
        self.assertEqual(self.clock.waits, [])
        self.assertEqual(result.to_manifest()["snapshot_id"], expected.snapshot["snapshot_id"])

    def test_429_and_transient_server_errors_then_success(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.clock = FakeClock()
                task, calls, expected = self.task(actions=[MetadataHTTPError(status), "success"])
                result = self.run_task(task)
                self.assertEqual(result.status, Status.SUCCESS)
                self.assertEqual((result.attempts, result.requests), (2, 2))
                self.assertEqual(self.clock.waits, [1])
                self.assertEqual(result.snapshot, expected.snapshot)

    def test_401_403_and_ordinary_404_are_terminal(self):
        for status, reason in ((401, Reason.AUTHENTICATION), (403, Reason.FORBIDDEN), (404, Reason.TARGET_UNAVAILABLE)):
            with self.subTest(status=status):
                task, calls, _ = self.task(actions=[MetadataHTTPError(status), "success"])
                result = self.run_task(task)
                self.assertEqual((result.status, result.reason), (Status.FAILED, reason))
                self.assertEqual(len(calls), 1)
                self.assertIsNone(result.snapshot)
                self.assertEqual(self.clock.waits, [])

    def test_nim_404_is_only_metadata_unavailable_for_selected_tag(self):
        task, calls, _ = self.task("nvidia-nim-metadata", actions=[MetadataHTTPError(404), "success"])
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason), (Status.FAILED, Reason.NIM_TAG_UNAVAILABLE))
        self.assertEqual(result.selection["tag"], "1.5.0")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(result.snapshot)
        self.assertNotIn("delete", json.dumps(result.to_manifest()).lower())

    def test_invalid_json_schema_identity_and_selection_are_not_retried(self):
        for error, reason in ((MetadataResponseError("SYNTHETIC body"), Reason.INVALID_JSON),
                              (json.JSONDecodeError("SYNTHETIC", "fixture", 0), Reason.INVALID_JSON),
                              (ValueError("SYNTHETIC schema"), Reason.INVALID_SCHEMA),
                              (ExecutionError(Reason.IDENTITY), Reason.IDENTITY),
                              (ExecutionError(Reason.SELECTION), Reason.SELECTION)):
            with self.subTest(reason=reason):
                task, calls, _ = self.task(actions=[error, "success"])
                result = self.run_task(task)
                self.assertEqual((result.status, result.reason), (Status.FAILED, reason))
                self.assertEqual(len(calls), 1)
                self.assertEqual(self.clock.waits, [])

    def test_non_idempotent_operation_is_never_retried(self):
        task, calls, _ = self.task(actions=[MetadataHTTPError(503), "success"])
        result = self.run_task(replace(task, idempotent=False))
        self.assertEqual((result.status, result.reason), (Status.FAILED, Reason.PROVIDER))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.clock.waits, [])

    def test_policy_can_disable_transient_status_and_transport_retries(self):
        for error in (MetadataHTTPError(503), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                task, calls, _ = self.task(actions=[error, "success"], retry_http_statuses=frozenset(), retry_transport_errors=False)
                self.assertEqual(self.run_task(task).status, Status.FAILED)
                self.assertEqual(len(calls), 1)

    def test_request_budget_zero_or_exhausted_never_dispatches_an_extra_call(self):
        task, calls, _ = self.task(max_requests=0)
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason, result.requests), (Status.DEFERRED, Reason.REQUEST_BUDGET, 0))
        self.assertEqual(calls, [])
        task, calls, _ = self.task(actions=[MetadataHTTPError(429), "success"], max_requests=1)
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason, result.requests), (Status.DEFERRED, Reason.REQUEST_BUDGET, 1))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.clock.waits, [])

    def test_multiple_requests_in_one_attempt_share_the_budget(self):
        task, _, observation = self.task(max_requests=1)
        calls = []
        def operation(context):
            context.request(task.resources[0], lambda remaining: calls.append(remaining))
            return context.request(task.resources[0], lambda remaining: observation)
        result = self.run_task(replace(task, operation=operation))
        self.assertEqual(result.reason, Reason.REQUEST_BUDGET)
        self.assertEqual((result.attempts, result.requests), (1, 1))
        self.assertEqual(len(calls), 1)
        self.assertIsNone(result.snapshot)

    def test_attempt_limit_terminates_zero_delay_transient_failures(self):
        task, calls, _ = self.task(actions=[MetadataHTTPError(503)] * 10,
                                   max_attempts=3, max_requests=10, max_delay_seconds=0, backoff_seconds=0)
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason), (Status.DEFERRED, Reason.ATTEMPT_BUDGET))
        self.assertEqual((result.attempts, result.requests, len(calls)), (3, 3, 3))
        self.assertEqual(self.clock.waits, [])

    def test_time_budget_exhausted_before_first_attempt(self):
        task, calls, _ = self.task(total_seconds=5)
        times = iter([0, 5])
        runtime = replace(self.clock.runtime(), monotonic=lambda: next(times))
        result = self.run_task(task, runtime)
        self.assertEqual((result.status, result.reason, result.attempts), (Status.DEFERRED, Reason.TIME_BUDGET, 0))
        self.assertEqual(calls, [])

    def test_slow_request_overrun_never_publishes_its_otherwise_valid_snapshot(self):
        task, calls, observation = self.task(total_seconds=5)
        def slow(remaining):
            self.assertEqual(remaining, 5)
            self.clock.now += 6
            return observation
        task, _, _ = self.task(actions=[slow], total_seconds=5)
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason), (Status.DEFERRED, Reason.TIME_BUDGET))
        self.assertEqual(result.elapsed_seconds, 6)
        self.assertTrue(result.to_manifest()["budget"]["overrun"])
        self.assertIsNone(result.snapshot)

    def test_local_normalization_time_is_counted_without_network_requests(self):
        task, _, observation = self.task(total_seconds=5, max_requests=0)
        def operation(context):
            self.clock.now = 5
            return observation
        result = self.run_task(replace(task, operation=operation))
        self.assertEqual((result.reason, result.requests), (Reason.TIME_BUDGET, 0))
        self.assertIsNone(result.snapshot)

    def test_final_result_validation_is_in_budget_before_publication(self):
        task, _, _ = self.task(total_seconds=5)
        clock = self.clock
        class SlowResult(SourceResult):
            def __post_init__(self):
                super().__post_init__()
                if self.status == Status.SUCCESS:
                    clock.now += 6
        with patch("discovery_execution.SourceResult", SlowResult):
            result = self.run_task(task)
        self.assertEqual((result.status, result.reason), (Status.DEFERRED, Reason.TIME_BUDGET))
        self.assertEqual(result.elapsed_seconds, 6)
        self.assertIsNone(result.snapshot)

    def test_retry_after_seconds_is_a_minimum_not_shortened_by_backoff(self):
        task, calls, _ = self.task(actions=[MetadataHTTPError(429, retry_after=parse_retry_after("7")), "success"])
        result = self.run_task(task)
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(self.clock.waits, [7])
        self.assertEqual(calls, [30, 23])

    def test_explicit_legacy_http_error_filters_only_retry_after_at_the_boundary(self):
        error = HTTPError("https://example.test/?token=SYNTHETIC", 429, "SYNTHETIC", {
            "Retry-After": "7", "Set-Cookie": "SYNTHETIC-CREDENTIAL",
        }, None)
        task, _, _ = self.task(actions=[error, "success"])
        result = self.run_task(task)
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(self.clock.waits, [7])
        self.assertNotIn("SYNTHETIC", json.dumps(result.to_manifest()))

    def test_retry_after_http_date_and_past_date_with_injected_wall_clock(self):
        for date, delay in (("Tue, 27 Oct 2026 12:00:07 GMT", 7), ("Tue, 27 Oct 2026 11:59:00 GMT", 1),
                            ("Tue Oct 27 12:00:07 2026", 7), ("Tuesday, 27-Oct-26 12:00:07 GMT", 7)):
            with self.subTest(date=date):
                self.clock = FakeClock()
                task, _, _ = self.task(actions=[MetadataHTTPError(503, retry_after=parse_retry_after(date)), "success"])
                self.assertEqual(self.run_task(task).status, Status.SUCCESS)
                self.assertEqual(self.clock.waits, [delay])

    def test_rfc850_century_uses_injected_time_and_the_fifty_year_cutoff(self):
        weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        for date, deferred in ((datetime(2070, 10, 27, 12), True),
                               (datetime(2076, 10, 27, 12), True),
                               (datetime(1990, 10, 27, 12), False),
                               (datetime(1976, 10, 27, 12, 0, 1), False)):
            with self.subTest(year=date.year):
                self.clock = FakeClock()
                raw = f"{weekdays[date.weekday()]}, 27-Oct-{date.year % 100:02d} 12:00:{date.second:02d} GMT"
                task, calls, _ = self.task(actions=[MetadataHTTPError(503, retry_after=parse_retry_after(raw)), "success"])
                result = self.run_task(task)
                self.assertEqual(result.status, Status.DEFERRED if deferred else Status.SUCCESS)
                self.assertEqual(self.clock.waits, [] if deferred else [1])
                self.assertEqual(len(calls), 1 if deferred else 2)

    def test_absent_or_invalid_retry_after_uses_local_backoff(self):
        for value in (None, "", "-1", "1.5", "SYNTHETIC", "Tue, 99 Oct 2026 12:00:00 GMT"):
            with self.subTest(value=value):
                self.clock = FakeClock()
                task, _, _ = self.task(actions=[MetadataHTTPError(429, retry_after=parse_retry_after(value)), "success"])
                self.assertEqual(self.run_task(task).status, Status.SUCCESS)
                self.assertEqual(self.clock.waits, [1])

    def test_retry_after_exceeding_time_or_delay_is_deferred_without_sleep(self):
        for delay, total, maximum, reason in ((20, 5, 30, Reason.RETRY_AFTER_BUDGET),
                                               (6, 30, 5, Reason.DELAY_LIMIT),
                                               (5, 5, 10, Reason.RETRY_AFTER_BUDGET)):
            with self.subTest(delay=delay, total=total):
                task, calls, _ = self.task(actions=[MetadataHTTPError(429, retry_after=RetryAfter(seconds=delay))],
                                           total_seconds=total, max_delay_seconds=maximum)
                result = self.run_task(task)
                self.assertEqual((result.status, result.reason), (Status.DEFERRED, reason))
                self.assertEqual(len(calls), 1)
                self.assertEqual(self.clock.waits, [])

    def test_extreme_numeric_retry_after_is_deferred_not_ignored(self):
        task, calls, _ = self.task(actions=[MetadataHTTPError(429, retry_after=parse_retry_after("9" * 5000))])
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason), (Status.DEFERRED, Reason.RETRY_AFTER_EXTREME))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.clock.waits, [])

    def test_exponential_backoff_and_deterministic_additive_jitter(self):
        values = iter([0.25, 0.5])
        runtime = replace(self.clock.runtime(), jitter=lambda base: next(values))
        task, _, _ = self.task(actions=[MetadataHTTPError(503), MetadataHTTPError(503), "success"])
        result = self.run_task(task, runtime)
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(self.clock.waits, [1.25, 2.5])
        self.assertEqual(result.wait_seconds, 3.75)

    def test_jitter_and_backoff_saturate_at_delay_limit(self):
        self.clock.added_jitter = 1e300
        task, _, _ = self.task(actions=[MetadataHTTPError(503)] * 4 + ["success"], max_delay_seconds=3)
        result = self.run_task(task)
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(self.clock.waits, [3, 3, 3, 3])
        self.assertEqual(self.clock.jitter_inputs, [1, 2, 3, 3])

    def test_backoff_that_uses_remaining_time_does_not_sleep_to_deadline(self):
        task, _, _ = self.task(actions=[MetadataHTTPError(503)], total_seconds=1)
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason), (Status.DEFERRED, Reason.TIME_BUDGET))
        self.assertEqual(self.clock.waits, [])

    def test_jitter_computation_is_in_the_time_budget(self):
        def jitter(base):
            self.clock.now += 6
            return 0
        runtime = replace(self.clock.runtime(), jitter=jitter)
        task, _, _ = self.task(actions=[MetadataHTTPError(503)], total_seconds=5)
        self.assertEqual(self.run_task(task, runtime).reason, Reason.TIME_BUDGET)
        self.assertEqual(self.clock.waits, [])

    def test_premature_or_failing_wait_never_retries_early(self):
        for sleep, reason, status in ((lambda delay: None, Reason.WAIT_INTERRUPTED, Status.DEFERRED),
                                      (lambda delay: (_ for _ in ()).throw(RuntimeError("SYNTHETIC")), Reason.RUNTIME, Status.FAILED)):
            with self.subTest(reason=reason):
                task, calls, _ = self.task(actions=[MetadataHTTPError(429), "success"])
                result = self.run_task(task, replace(self.clock.runtime(), sleep=sleep))
                self.assertEqual((result.status, result.reason), (status, reason))
                self.assertEqual(len(calls), 1)

    def test_failing_or_oversleeping_wait_keeps_actual_consumed_time(self):
        def failing(delay):
            self.clock.now += 2
            raise RuntimeError("SYNTHETIC wait detail")
        task, calls, _ = self.task(actions=[MetadataHTTPError(429), "success"])
        result = self.run_task(task, replace(self.clock.runtime(), sleep=failing))
        self.assertEqual((result.reason, result.elapsed_seconds, result.wait_seconds), (Reason.RUNTIME, 2, 2))
        self.assertEqual(len(calls), 1)
        self.clock = FakeClock()
        task, calls, _ = self.task(actions=[MetadataHTTPError(503), "success"], total_seconds=5)
        def oversleep(delay): self.clock.now += 6
        result = self.run_task(task, replace(self.clock.runtime(), sleep=oversleep))
        self.assertEqual((result.status, result.reason), (Status.DEFERRED, Reason.TIME_BUDGET))
        self.assertEqual((result.elapsed_seconds, result.wait_seconds, len(calls)), (6, 6, 1))

    def test_invalid_jitter_and_backwards_clock_fail_without_raw_diagnostics(self):
        for jitter in (lambda _: -1, lambda _: float("nan"), lambda _: True):
            with self.subTest(jitter=jitter):
                task, _, _ = self.task(actions=[MetadataHTTPError(503)])
                self.assertEqual(self.run_task(task, replace(self.clock.runtime(), jitter=jitter)).reason, Reason.RUNTIME)
        task, _, observation = self.task()
        def backwards(remaining):
            self.clock.now = -1
            return observation
        task, _, _ = self.task(actions=[backwards])
        self.assertEqual(self.run_task(task).reason, Reason.RUNTIME)

    def test_304_cannot_be_unchanged_without_a_validated_cache(self):
        task, calls, _ = self.task(actions=[MetadataHTTPError(304), "success"])
        result = self.run_task(task)
        self.assertEqual((result.status, result.reason), (Status.FAILED, Reason.CACHE_REQUIRED))
        self.assertNotEqual(result.status, Status.UNCHANGED)
        self.assertIsNone(result.snapshot)
        self.assertEqual(len(calls), 1)

    def test_interrupted_http_request_retries_in_executor_only_and_matches_b33(self):
        task, _, observation = self.task(total_seconds=2)
        payload = json.loads((ROOT / "fixtures/contracts_b40/inputs.synthetic.json").read_text())["huggingface"]
        outcomes = iter([IncompleteRead(b"SYNTHETIC-PARTIAL", 10), HTTPResult(200, json.dumps(payload).encode())])
        class Transport:
            calls = 0
            timeouts = []
            def fetch(self, request, *, timeout, max_bytes):
                self.calls += 1
                self.timeouts.append(timeout)
                result = next(outcomes)
                if isinstance(result, Exception): raise result
                return result
        transport = Transport()
        def operation(context):
            def read(remaining):
                return get_metadata_json("https://metadata.example.test/models", policy=HTTPPolicy(
                    frozenset({"metadata.example.test"}), 10000, min(20, remaining)), transport=transport)
            raw = context.request(task.resources[0], read)
            record = normalize_huggingface_model(raw)
            return SourceObservation(make_snapshot([record], scope=observation.snapshot["scope"],
                                                  captured_at=observation.snapshot["captured_at"]), True)
        result = self.run_task(replace(task, operation=operation))
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(result.snapshot, observation.snapshot)
        self.assertEqual(transport.calls, 2)
        self.assertEqual(transport.timeouts, [2, 1])
        self.assertEqual(self.clock.waits, [1])

    def test_failure_of_one_source_does_not_discard_another_snapshot(self):
        first, _, _ = self.task(actions=[MetadataHTTPError(401)])
        second, _, expected = self.task("moark")
        report = execute_sources([first, second], runtime=self.clock.runtime())
        self.assertEqual([r.status for r in report.results], [Status.FAILED, Status.SUCCESS])
        self.assertEqual(report.successful_snapshots(), {"moark": expected.snapshot})
        manifest = report.to_manifest()
        self.assertFalse(manifest["complete"])
        self.assertEqual(manifest["requested_sources"], ["huggingface", "moark"])
        self.assertIsNone(manifest["sources"][0]["snapshot_id"])

    def test_source_time_budgets_are_independent_even_after_an_overrun(self):
        first, _, _ = self.task(total_seconds=5)
        def slow(remaining):
            self.clock.now += 6
            raise TimeoutError()
        first, _, _ = self.task(actions=[slow], total_seconds=5)
        second, _, _ = self.task("moark", total_seconds=5)
        report = execute_sources([first, second], runtime=self.clock.runtime())
        self.assertEqual(report.results[0].status, Status.DEFERRED)
        self.assertEqual(report.results[1].status, Status.SUCCESS)
        self.assertEqual(report.results[1].elapsed_seconds, 0)

    def test_batch_owns_all_source_plans_before_first_callback(self):
        first, _, first_observation = self.task()
        second, _, second_observation = self.task("csghub")
        expected = deepcopy(second.selection)
        def operation(context):
            second.selection["ids"] = ["different/model"]
            return first_observation
        report = execute_sources([replace(first, operation=operation), second], runtime=self.clock.runtime())
        self.assertEqual([result.status for result in report.results], [Status.SUCCESS, Status.SUCCESS])
        self.assertEqual(report.results[1].selection, expected)
        self.assertEqual(report.results[1].snapshot, second_observation.snapshot)

    def test_incomplete_selection_never_publishes_a_reduced_scope(self):
        task, _, observation = self.task()
        source_entry = observation.snapshot["records"][0]
        record = SourceRecord(**{k: v for k, v in source_entry.items() if k not in {"record_key", "payload_sha256"}})
        selection = deepcopy(task.selection)
        selection["ids"].append("missing/model")
        refs = task.resources + (ResourceRef("huggingface", "missing/model"),)
        partial = make_snapshot([record], scope={task.source: selection}, captured_at=observation.snapshot["captured_at"])
        policy = replace(task.policy, resources=frozenset(refs))
        for complete in (True, False):
            with self.subTest(complete=complete):
                changed = replace(task, resources=refs, selection=selection, policy=policy,
                                  operation=lambda ctx: SourceObservation(partial, complete))
                result = self.run_task(changed)
                self.assertEqual((result.status, result.reason), (Status.FAILED, Reason.INCOMPLETE))
                self.assertEqual(result.to_manifest()["selection"]["ids"], selection["ids"])
                self.assertFalse(result.complete)
                self.assertIsNone(result.snapshot)

    def test_corrupt_empty_or_wrong_identity_snapshots_are_terminal(self):
        task, _, observation = self.task()
        empty = deepcopy(observation.snapshot)
        empty["records"] = []
        corrupt = deepcopy(observation.snapshot)
        corrupt["records"][0]["display_name"] = "changed without digest"
        other = discover_fixtures(sources=["moark"])
        for data in (empty, corrupt, other):
            with self.subTest(data=data["snapshot_id"]):
                result = self.run_task(replace(task, operation=lambda ctx: SourceObservation(data, True)))
                self.assertEqual(result.status, Status.FAILED)
                self.assertEqual(result.attempts, 1)
                self.assertIsNone(result.snapshot)

    def test_output_revision_nullability_respects_source_spec(self):
        for source, revision in (("models.dev", None), ("moark", "b" * 40)):
            with self.subTest(source=source):
                task, _, observation = self.task(source)
                entry = observation.snapshot["records"][0]
                record = SourceRecord(**{k: v for k, v in entry.items() if k not in {"record_key", "payload_sha256"}})
                invalid = make_snapshot([replace(record, source_revision=revision)], scope=observation.snapshot["scope"],
                                        captured_at=observation.snapshot["captured_at"])
                result = self.run_task(replace(task, operation=lambda ctx: SourceObservation(invalid, True)))
                self.assertEqual((result.status, result.reason), (Status.FAILED, Reason.INVALID_SCHEMA))
                self.assertEqual(result.attempts, 1)
                self.assertIsNone(result.snapshot)

    def test_resources_are_checked_before_dispatch_and_context_cannot_be_reused(self):
        task, calls, observation = self.task()
        other = ResourceRef("moark", "Qwen3-8B")
        result = self.run_task(replace(task, policy=replace(task.policy, resources=frozenset({other}))))
        self.assertEqual((result.reason, result.attempts, result.requests), (Reason.SELECTION, 0, 0))
        self.assertEqual(calls, [])
        captured = []
        def operation(context):
            captured.append(context)
            return context.request(task.resources[0], lambda _: observation)
        result = self.run_task(replace(task, operation=operation))
        self.assertEqual(result.status, Status.SUCCESS)
        with self.assertRaises(ExecutionError):
            captured[0].request(task.resources[0], lambda _: self.fail("Closed context dispatched a request"))

    def test_request_cannot_switch_to_another_source_even_if_policy_allows_it(self):
        task, _, _ = self.task()
        other = ResourceRef("moark", "Qwen3-8B")
        def operation(context):
            return context.request(other, lambda _: self.fail("Cross-source request dispatched"))
        changed = replace(task, operation=operation, policy=replace(task.policy, resources=task.policy.resources | {other}))
        result = self.run_task(changed)
        self.assertEqual((result.status, result.reason, result.requests), (Status.FAILED, Reason.SELECTION, 0))

    def test_callback_mutating_callers_plan_cannot_change_the_published_selection(self):
        task, _, observation = self.task()
        expected = deepcopy(task.selection)
        def operation(context):
            task.selection["ids"] = ["changed/by-caller"]
            return observation
        result = self.run_task(replace(task, operation=operation))
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(result.selection, expected)
        self.assertEqual(result.snapshot, observation.snapshot)

    def test_positive_results_require_valid_snapshots_and_failed_ones_forbid_them(self):
        task, _, observation = self.task()
        result = self.run_task(task)
        with self.assertRaises(ValueError):
            replace(result, snapshot=None)
        with self.assertRaises(ValueError):
            replace(result, status=Status.FAILED, complete=False, reason=Reason.PROVIDER)
        # The schema reserves unchanged for B4.5; execution never derives it from 304.
        unchanged = replace(result, status=Status.UNCHANGED)
        self.assertEqual(unchanged.to_manifest()["snapshot_id"], observation.snapshot["snapshot_id"])
        result.snapshot["records"][0]["display_name"] = "tampered"
        with self.assertRaises(ValueError):
            result.to_manifest()

    def test_diagnostics_and_manifests_never_include_exception_text_body_or_headers(self):
        marker = "SYNTHETIC-PRIVATE-DO-NOT-USE"
        errors = [ValueError(marker), RuntimeError(marker),
                  HTTPError("https://example.test/?token=" + marker, 401, marker, {"Set-Cookie": marker}, None)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                task, _, _ = self.task(actions=[error])
                result = self.run_task(task)
                manifest = ExecutionReport((result,)).to_manifest()
                encoded = json.dumps(manifest)
                self.assertNotIn(marker, encoded)
                self.assertNotIn("Set-Cookie", encoded)
                self.assertNotIn("example.test", encoded)
                self.assertIsNone(manifest["sources"][0]["snapshot_id"])

    def test_malformed_http_status_or_unsafe_error_string_cannot_break_classification(self):
        task, _, _ = self.task()
        class Sensitive(ValueError):
            def __str__(self): raise AssertionError("Exception text inspected")
        for error, expected in ((HTTPError("", [], "SYNTHETIC", {}, None), Reason.INVALID_SCHEMA),
                                (Sensitive(), Reason.INVALID_SCHEMA)):
            with self.subTest(error=type(error).__name__):
                changed, calls, _ = self.task(actions=[error, "success"])
                result = self.run_task(changed)
                self.assertEqual((result.status, result.reason), (Status.FAILED, expected))
                self.assertEqual(len(calls), 1)

    def test_real_synthetic_and_mixed_manifest_labels_are_explicit_declarations(self):
        first, _, _ = self.task()
        second, _, _ = self.task("csghub")
        # Simulate a declared real execution using fixture data, without any I/O.
        report = execute_sources([first, replace(second, synthetic=False)], runtime=self.clock.runtime())
        manifest = report.to_manifest()
        self.assertEqual(manifest["data_kind"], "mixed")
        self.assertEqual([item["synthetic"] for item in manifest["sources"]], [True, False])
        self.assertEqual(manifest["sources"][0]["requested_resources"], [{
            "source": first.source, "source_id": first.resources[0].source_id,
        }])

    def test_invalid_runtime_never_dispatches_or_returns_a_positive_result(self):
        task, calls, _ = self.task()
        result = self.run_task(task, replace(self.clock.runtime(), monotonic=lambda: float("nan")))
        self.assertEqual((result.status, result.reason), (Status.FAILED, Reason.RUNTIME))
        self.assertEqual((result.attempts, result.requests, calls), (0, 0, []))
        task, _, _ = self.task(actions=[MetadataHTTPError(429, retry_after=parse_retry_after("Tue, 27 Oct 2026 12:00:07 GMT"))])
        result = self.run_task(task, replace(self.clock.runtime(), wall_time=lambda: float("nan")))
        self.assertEqual(result.reason, Reason.RUNTIME)
        self.assertIsNone(result.snapshot)

    def test_seven_offline_source_results_preserve_all_b33_references(self):
        reference = json.loads((ROOT / "fixtures/contracts_b40/reference.b33.json").read_text())
        tasks = []
        for source in reference["sources"]:
            task, _, observation = self.task(source, max_requests=0)
            tasks.append(replace(task, operation=lambda ctx, obs=observation: obs))
        report = execute_sources(tasks, runtime=self.clock.runtime())
        self.assertTrue(report.to_manifest()["complete"])
        self.assertEqual(report.to_manifest()["data_kind"], "synthetic")
        for result in report.results:
            self.assertEqual(result.snapshot, reference["sources"][result.source]["snapshot"])
            self.assertEqual(result.requests, 0)

    def test_policy_validation_refuses_unsafe_limits_or_permanent_retry_codes(self):
        task, _, _ = self.task()
        for changes in ({"max_requests": -1}, {"max_requests": True}, {"max_requests": 10**400},
                        {"max_attempts": 0}, {"max_attempts": 10**400},
                        {"total_seconds": 0}, {"total_seconds": float("inf")},
                        {"max_delay_seconds": -1}, {"backoff_seconds": 11},
                        {"resources": frozenset()}, {"retry_http_statuses": {401}},
                        {"retry_http_statuses": {429.0}},
                        {"retry_http_statuses": {403, 404}}, {"retry_http_statuses": {304}},
                        {"retry_transport_errors": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(task.policy, **changes)

    def test_sensitive_selection_or_identifier_is_refused_not_redacted_into_a_new_scope(self):
        task, _, _ = self.task()
        for selection in ({**task.selection, "Authorization": "SYNTHETIC"},
                          {**task.selection, "ids": ["https://example.test/?token=SYNTHETIC"]},
                          {**task.selection, "account": "SYNTHETIC"}):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                replace(task, selection=selection)
        with self.assertRaises(ValueError):
            ResourceRef("huggingface", "https://example.test/?token=SYNTHETIC")

    def test_duplicate_sources_in_one_report_or_batch_are_rejected(self):
        task, _, _ = self.task()
        with self.assertRaises(ValueError):
            execute_sources([task, task], runtime=self.clock.runtime())
        result = self.run_task(task)
        with self.assertRaises(ValueError):
            ExecutionReport((result, result))


if __name__ == "__main__":
    unittest.main()
