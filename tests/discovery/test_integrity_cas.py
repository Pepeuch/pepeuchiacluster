"""Offline regression cases; no provider, real database or credential fixtures."""

from copy import deepcopy
from dataclasses import replace
import io
import secrets
import unittest
from unittest.mock import patch

from discovery_cache import compare_snapshots, make_snapshot, validate_snapshot
from discovery_provenance import make_provenance, validate_provenance
from discovery_registry import discover_fixtures
from discovery_import_contract import validate_transition
from emit_discovery_import import emit_pg, emit_surreal
from incremental_import_plan import plan_import
from source_adapters import SourceRecord
from tests.discovery.test_incremental_import_plan import entry


def records(snapshot):
    return [SourceRecord(**{k: deepcopy(v) for k, v in r.items()
                           if k not in {"record_key", "payload_sha256"}}) for r in snapshot["records"]]


class Offline(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("Offline integrity test"))
            guard.start()
            self.addCleanup(guard.stop)
        self.snapshot = discover_fixtures(sources=["models.dev"])


class Integrity(Offline):
    def test_missing_or_null_capture_never_defaults_to_current_time(self):
        for missing in (True, False):
            data = deepcopy(self.snapshot)
            if missing:
                data.pop("captured_at")
            else:
                data["captured_at"] = None
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_unknown_envelope_fields_are_refused_before_either_emitter_writes(self):
        data = deepcopy(self.snapshot)
        data["unbound_field"] = {"future": True}
        for emitter in (emit_pg, emit_surreal):
            output = io.StringIO()
            with self.assertRaises(ValueError):
                emitter(data, output)
            self.assertEqual(output.getvalue(), "")

    def test_missing_capture_is_refused_without_partial_sql(self):
        data = deepcopy(self.snapshot)
        data.pop("captured_at")
        for emitter in (emit_pg, emit_surreal):
            output = io.StringIO()
            with self.assertRaises(ValueError):
                emitter(data, output)
            self.assertEqual(output.getvalue(), "")

    def test_scope_equality_keeps_json_types_distinct(self):
        for left, right in ((False, 0), (True, 1), (0, 0.0), (None, [])):
            a = make_snapshot(records(self.snapshot), scope={"observed": left}, captured_at=self.snapshot["captured_at"])
            b = make_snapshot(records(self.snapshot), scope={"observed": right}, captured_at=self.snapshot["captured_at"])
            self.assertNotEqual(a["snapshot_id"], b["snapshot_id"])
            with self.assertRaises(ValueError):
                compare_snapshots(a, b)

    def test_attested_scope_cannot_change_false_to_zero_without_resigning(self):
        snapshot = make_snapshot(records(self.snapshot), scope={"observed": False}, captured_at=self.snapshot["captured_at"])
        key = secrets.token_bytes(32)
        context = {"domain": "fixtures.invalid", "account_partition": "anonymous", "representation": "metadata-v1"}
        provenance = make_provenance(snapshot, kind="controlled_observation", context=context, issuer="simulated", key=key)
        altered = deepcopy(provenance)
        altered["scope"]["observed"] = 0
        with self.assertRaises(ValueError):
            validate_provenance(snapshot, altered, trusted_issuers={"simulated": key})

    def test_unknown_payload_values_and_valid_snapshot_are_preserved(self):
        item = replace(records(self.snapshot)[0], attributes={"future": {"null": None, "false": False, "zero": 0, "empty": []}})
        snapshot = make_snapshot([item], scope=self.snapshot["scope"], captured_at=self.snapshot["captured_at"])
        original = deepcopy(snapshot)
        self.assertIs(validate_snapshot(snapshot), snapshot)
        self.assertEqual(snapshot, original)
        self.assertIsNone(snapshot["records"][0]["attributes"]["future"]["null"])
        self.assertIs(snapshot["records"][0]["attributes"]["future"]["false"], False)
        self.assertEqual(type(snapshot["records"][0]["attributes"]["future"]["zero"]), int)

    def test_pg_copy_preserves_empty_revision_separately_from_null(self):
        template = records(self.snapshot)[0]
        for revision, token in ((None, ""), ("", '""'), ('comma,"quote"', '"comma,""quote"""')):
            snapshot = make_snapshot([replace(template, source_revision=revision)], scope=self.snapshot["scope"],
                                     captured_at=self.snapshot["captured_at"])
            output = io.StringIO()
            emit_pg(snapshot, output)
            row = output.getvalue().split("HEADER true);\n", 1)[1].splitlines()[1]
            self.assertTrue(row.split(",", 4)[4].startswith(token+","))

    def test_emission_keeps_a_defensive_copy_if_caller_changes_snapshot_during_output(self):
        for emitter in (emit_pg, emit_surreal):
            snapshot = deepcopy(self.snapshot)
            class CallerStream(io.StringIO):
                def write(self, value):
                    snapshot["records"][0]["attributes"]["external_mutation"] = True
                    return super().write(value)
            output = CallerStream()
            emitter(snapshot, output, expected_snapshot=None)
            self.assertTrue(snapshot["records"][0]["attributes"]["external_mutation"])
            self.assertNotIn("external_mutation", output.getvalue())


class CASGeneration(Offline):
    def changed(self, *, time="2026-10-28T12:00:00+00:00", revision="synthetic-r2"):
        # Revisions are opaque: lexical order is deliberately irrelevant.
        return make_snapshot([replace(r, source_revision=revision) for r in records(self.snapshot)],
                             scope=self.snapshot["scope"], captured_at=time)

    def test_plan_accepts_equivalent_instant_without_rewriting_snapshot(self):
        other = deepcopy(self.snapshot)
        other["captured_at"] = "2026-10-27T02:00:00+02:00"
        original = deepcopy(other)
        plan = plan_import(entry(self.snapshot), entry(other))
        self.assertFalse(plan["executable"])
        self.assertEqual(plan["changes"]["changed"], [])
        self.assertEqual(other, original)

    def test_transition_keeps_microseconds_and_opaque_revisions(self):
        first = self.changed(time="9999-01-01T00:00:00.000001+00:00", revision="z-tag")
        next_observation = self.changed(time="9999-01-01T00:00:00.000002+00:00", revision="a-tag")
        validate_transition(first, next_observation)
        with self.assertRaises(ValueError):
            validate_transition(next_observation, first)

    def test_both_emitters_require_expected_or_already_applied_state_under_transaction(self):
        changed = self.changed()
        for emitter in (emit_pg, emit_surreal):
            output = io.StringIO()
            emitter(changed, output, expected_snapshot=self.snapshot)
            sql = output.getvalue()
            self.assertIn("Discovery CAS precondition failed", sql)
            self.assertLess(sql.index("Discovery CAS precondition failed"), sql.rindex("COMMIT"))
            self.assertIn(self.snapshot["snapshot_id"], sql)
            self.assertIn(changed["snapshot_id"], sql)
        output = io.StringIO()
        emit_pg(changed, output, expected_snapshot=self.snapshot)
        sql = output.getvalue()
        self.assertLess(sql.index("LOCK TABLE"), sql.index("DO $discovery_cas$"))
        self.assertLess(sql.index("DO $discovery_cas$"), sql.index("INSERT INTO poc.discovery_cache"))
        self.assertIn("e.record_key IS NULL", sql)

    def test_initial_cas_is_explicit_absence_not_default_legacy_update(self):
        for emitter in (emit_pg, emit_surreal):
            default, guarded = io.StringIO(), io.StringIO()
            emitter(self.snapshot, default)
            emitter(self.snapshot, guarded, expected_snapshot=None)
            self.assertNotIn("Discovery CAS precondition failed", default.getvalue())
            self.assertIn("Discovery CAS precondition failed", guarded.getvalue())

    def test_invalid_transition_leaves_output_untouched(self):
        newer = self.changed()
        incompatible = deepcopy(newer)
        incompatible["scope"] = {"models.dev": {"mode": "first_n_sorted", "limit": 9}}
        for before, after in ((newer, self.snapshot), (self.snapshot, incompatible)):
            for emitter in (emit_pg, emit_surreal):
                output = io.StringIO()
                with self.assertRaises(ValueError):
                    emitter(after, output, expected_snapshot=before)
                self.assertEqual(output.getvalue(), "")

    def test_cas_output_owns_no_mutable_snapshot_and_does_not_touch_unobserved_rows(self):
        before, after = deepcopy(self.snapshot), self.changed()
        original = deepcopy((before, after))
        for emitter in (emit_pg, emit_surreal):
            output = io.StringIO()
            emitter(after, output, expected_snapshot=before)
            self.assertNotIn("DELETE", output.getvalue())
            self.assertNotIn("external_models", output.getvalue())
        self.assertEqual((before, after), original)

    def test_protected_transition_requires_trusted_origin_context_and_anonymous_partition(self):
        from discovery_provenance import emit_protected_transition
        before, after = entry(self.snapshot), entry(self.changed())
        context = before["request"]["context"]
        for engine in ("pg", "surreal"):
            output = io.StringIO()
            with self.assertRaises(ValueError):
                emit_protected_transition(before, after, context=context, trusted_issuers={}, engine=engine, stream=output)
            self.assertEqual(output.getvalue(), "")
        key = secrets.token_bytes(32)
        trust = {"simulated": key}
        for cache in (before, after):
            from validated_discovery_cache import make_cache
            cache.update(make_cache(cache["request"], cache["snapshot"], make_provenance(
                cache["snapshot"], kind="controlled_observation", context=context, issuer="simulated", key=key),
                validators=cache["validators"], trusted_issuers=trust))
        for engine, emitter in (("pg", emit_pg), ("surreal", emit_surreal)):
            output, expected = io.StringIO(), io.StringIO()
            emit_protected_transition(before, after, context=context, trusted_issuers=trust, engine=engine, stream=output)
            emitter(after["snapshot"], expected, expected_snapshot=before["snapshot"])
            self.assertEqual(output.getvalue(), expected.getvalue())
            for changed_context, trusted in (({**context, "domain": "other.invalid"}, trust),
                                             ({**context, "account_partition": "private"}, trust), (context, {})):
                output = io.StringIO()
                with self.assertRaises(ValueError):
                    emit_protected_transition(before, after, context=changed_context, trusted_issuers=trusted, engine=engine, stream=output)
                self.assertEqual(output.getvalue(), "")
