"""Offline generation checks; real engine evidence belongs to a separate run."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path

from tests.discovery import POC_ROOT
import unittest
from unittest.mock import patch

from discovery_cache import canonical_json, make_snapshot
from discovery_registry import discover_fixtures
from emit_discovery_import import emit_pg, emit_surreal, observation_time
from source_adapters import SourceRecord


class ReplayGeneration(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("Offline generation only"))
            guard.start()
            self.addCleanup(guard.stop)
        self.snapshot = discover_fixtures()

    def emit(self, emitter, snapshot=None):
        output = io.StringIO()
        emitter(self.snapshot if snapshot is None else snapshot, output)
        return output.getvalue()

    def test_pg_guard_is_under_lock_before_any_target_write(self):
        sql = self.emit(emit_pg)
        markers = ["BEGIN;", "SET TRANSACTION ISOLATION LEVEL READ COMMITTED;",
                   "LOCK TABLE poc.discovery_cache IN SHARE ROW EXCLUSIVE MODE;",
                   "DO $discovery_guard$", "RAISE EXCEPTION", "INSERT INTO poc.discovery_cache", "COMMIT;"]
        positions = [sql.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("c.last_seen_at > s.last_seen_at", sql)
        self.assertIn("c.last_seen_at = s.last_seen_at", sql)
        self.assertIn("to_jsonb(c) IS DISTINCT FROM to_jsonb(s)", sql)

    def test_surreal_all_guards_and_writes_are_in_one_bounded_transaction(self):
        sql = self.emit(emit_surreal)
        self.assertTrue(sql.startswith("OPTION IMPORT;"))
        begin, commit = sql.index("BEGIN TRANSACTION;"), sql.index("COMMIT TRANSACTION;")
        self.assertEqual(sql.count("BEGIN TRANSACTION;"), 1)
        self.assertEqual(sql.count("COMMIT TRANSACTION;"), 1)
        self.assertTrue(sql.endswith("COMMIT TRANSACTION;\n"))
        create = sql.index("DEFINE TABLE IF NOT EXISTS discovery_cache SCHEMALESS;")
        self.assertLess(begin, create)
        self.assertLess(create, sql.index("LET $current"))
        for record in self.snapshot["records"]:
            check = sql.index("LET $current = (SELECT * FROM ONLY discovery_cache:" + record["record_key"])
            write = sql.index("UPSERT discovery_cache:" + record["record_key"])
            self.assertLess(begin, check)
            self.assertLess(check, write)
            self.assertLess(write, commit)
        self.assertIn("$seen > <datetime>", sql)
        self.assertIn("$seen = <datetime>", sql)
        self.assertIn("$payload !=", sql)

    def test_comparison_normalizes_instants_without_mutating_b2(self):
        baseline = deepcopy(self.snapshot)
        for value in ("2026-10-28T12:00:00Z", "2026-10-28T14:00:00+02:00", "2026-10-28T07:00:00-05:00"):
            snapshot = deepcopy(baseline)
            snapshot["captured_at"] = value
            sql = self.emit(emit_surreal, snapshot)
            self.assertIn('<datetime> "2026-10-28T12:00:00.000000Z"', sql)
            self.assertIn('"last_seen_at":' + canonical_json(value), sql)
            self.assertEqual(snapshot["snapshot_id"], baseline["snapshot_id"])
        self.assertEqual(self.snapshot, baseline)
        self.assertEqual(observation_time("2026-10-28T14:00:00.000001+02:00"), "2026-10-28T12:00:00.000001Z")

    def test_utf8_budget_checks_whole_output_and_never_emits_a_prefix(self):
        item = self.snapshot["records"][0]
        record = SourceRecord(**{k: v for k, v in item.items() if k not in {"record_key", "payload_sha256"}})
        self.snapshot = make_snapshot([replace(record, display_name="Synthétique 漢字")],
                                      scope=self.snapshot["scope"], captured_at=self.snapshot["captured_at"])
        sql = self.emit(emit_surreal)
        for budget in (len(sql.encode("utf-8")), len(sql.encode("utf-8")) - 1):
            stream = io.StringIO()
            with patch("emit_discovery_import.MAX_SURREAL_IMPORT_BYTES", budget):
                if budget == len(sql.encode("utf-8")):
                    emit_surreal(self.snapshot, stream)
                    self.assertEqual(stream.getvalue(), sql)
                else:
                    with self.assertRaisesRegex(ValueError, "UTF-8 byte budget"):
                        emit_surreal(self.snapshot, stream)
                    self.assertEqual(stream.getvalue(), "")
        self.assertGreater(len(sql.encode("utf-8")), len(sql))

    def test_snapshot_keys_unknowns_and_unobserved_resources_are_preserved(self):
        record = self.snapshot["records"][0]
        item = SourceRecord(**{k: v for k, v in record.items() if k not in {"record_key", "payload_sha256"}})
        item = replace(item, attributes={**item.attributes, "future": {"null": None, "false": False, "zero": 0, "empty": []}})
        snapshot = make_snapshot([item], scope=self.snapshot["scope"], captured_at=self.snapshot["captured_at"])
        original = canonical_json(snapshot)
        for emitter in (emit_pg, emit_surreal):
            sql = self.emit(emitter, snapshot)
            self.assertIn(record["record_key"], sql)
            self.assertNotIn("DELETE", sql)
            self.assertNotIn("external_models", sql)
            for missing in self.snapshot["records"][1:]:
                self.assertNotIn(missing["record_key"], sql)
        self.assertEqual(canonical_json(snapshot), original)

    def test_pg_invalid_copy_field_never_emits_partial_transaction(self):
        record = self.snapshot["records"][0]
        item = SourceRecord(**{k: v for k, v in record.items() if k not in {"record_key", "payload_sha256"}})
        snapshot = make_snapshot([replace(item, display_name="synthetic\n\\.\nname")],
                                 scope=self.snapshot["scope"], captured_at=self.snapshot["captured_at"])
        output = io.StringIO()
        with self.assertRaises(ValueError):
            emit_pg(snapshot, output)
        self.assertEqual(output.getvalue(), "")

    def test_retained_real_guard_artifacts_are_intact_and_not_benchmark_samples(self):
        root = POC_ROOT / "results/20261028-vm150-replay-guard"
        if not root.is_dir():
            self.skipTest("Private VM150 replay qualification exports are not distributed with Git")
        manifest = json.loads((root / "review-manifest.json").read_text())
        self.assertFalse(manifest["credentials_included"])
        self.assertFalse(manifest["performance_campaign_rerun"])
        for name, metadata in manifest["files"].items():
            raw = (root / name).read_bytes()
            self.assertEqual(len(raw), metadata["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata["sha256"])
        outcome = json.loads((root / manifest["final_attempt"] / "result.json").read_text())
        self.assertEqual(outcome["status"], "VERIFIED")
        self.assertEqual(outcome["mode"], "b2_qualification_only")
        self.assertEqual(outcome["stages"], [])
        self.assertTrue(outcome["historical_metadata_unchanged"])
        self.assertEqual(set(outcome["final_container_states"].values()), {"exited"})

    def test_real_replay_refusals_rollback_and_restore_have_explicit_scope(self):
        root = POC_ROOT / "results/20261028-vm150-replay-guard"
        if not root.is_dir():
            self.skipTest("Private VM150 replay qualification exports are not distributed with Git")
        outcome = json.loads((root / "attempt-20261028T204333Z-a15681/result.json").read_text())
        proof = outcome["discovery"]["regenerated_sql_replay_guard"]
        self.assertEqual({c["case"] for c in proof["cases"]}, {
            "old_revision_replay", "old_identical_payload_must_not_rewind_time",
            "same_instant_conflict_with_new_row_atomic_rollback"})
        for case in proof["cases"]:
            self.assertTrue(case["both_engines_unchanged"])
            self.assertEqual(case["postgres_exit"], 3)
            self.assertEqual(case["surreal_http_status"], 422)
        self.assertTrue(proof["equivalent_timezone_replay"])
        self.assertFalse(proof["old_pre_generated_sql_protected"])
        self.assertFalse(proof["capture_is_provider_revision_order"])
        self.assertFalse(proof["concurrent_engine_transactions_tested"])
        self.assertTrue(outcome["discovery"]["b2_restore_new_destinations"]["verified"])
        self.assertEqual(outcome["discovery"]["b2_restore_new_destinations"]["records"], 9)


if __name__ == "__main__":
    unittest.main()
