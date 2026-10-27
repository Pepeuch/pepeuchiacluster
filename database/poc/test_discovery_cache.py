"""Offline tests for B2 snapshot integrity, repeatability and dual SQL emitters."""

from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from collect_discovery_snapshot import collect_modelsdev
from discovery_cache import (
    compare_snapshots, make_snapshot, record_key, validate_snapshot,
)
from emit_discovery_import import emit_pg, emit_surreal
from source_adapters import SourceRecord


SCOPE = {"models.dev": {"mode": "first_n_sorted", "limit": 2}}


def sample(source="models.dev", entity_type="model_reference", source_id="foo"):
    return SourceRecord(
        source=source, entity_type=entity_type, source_id=source_id,
        source_revision="a" * 40, display_name="Foo", attributes={"open_weights": None},
        relationships=(), raw_metadata={"from": "fixture"},
    )


def snap(*records, time="2026-10-27T13:00:00+00:00", scope=None):
    return make_snapshot(records, scope=SCOPE if scope is None else scope, captured_at=time)


class DiscoveryCacheTests(unittest.TestCase):
    def test_identity_stable_across_revision_and_change_in_attributes(self):
        first = sample()
        changed = replace(first, source_revision="b" * 40, attributes={"open_weights": True})
        old, new = snap(first), snap(changed)
        self.assertEqual(old["records"][0]["record_key"], new["records"][0]["record_key"])
        self.assertNotEqual(old["records"][0]["payload_sha256"], new["records"][0]["payload_sha256"])
        self.assertEqual(len(compare_snapshots(old, new)["changed"]), 1)

    def test_repeat_is_idempotent_and_capture_time_not_content(self):
        first = snap(sample())
        again = snap(sample(), time="2026-10-27T13:05:00+00:00")
        self.assertEqual(first["snapshot_id"], again["snapshot_id"])
        self.assertEqual(compare_snapshots(first, again)["unchanged_count"], 1)

    def test_namespaces_prevent_cross_source_merges(self):
        self.assertNotEqual(
            record_key("huggingface", "model_artifact", "org/model"),
            record_key("modelscope", "model_artifact", "org/model"),
        )
        self.assertNotEqual(
            record_key("huggingface", "model_artifact", "org/model"),
            record_key("huggingface", "agent_resource", "org/model"),
        )
        # Future upstreams may expose a model file OR only an inference API.
        for rec in (
            sample(source="modelscope", entity_type="model_artifact"),
            sample(source="csghub", entity_type="agent_resource"),
            sample(source="moark", entity_type="inference_endpoint"),
        ):
            validate_snapshot(snap(rec))

    def test_conflicting_duplicate_rejected_but_exact_duplicate_deduplicated(self):
        original = sample()
        self.assertEqual(len(snap(original, original)["records"]), 1)
        with self.assertRaisesRegex(ValueError, "Conflicting records"):
            snap(original, replace(original, display_name="Different"))

    def test_snapshot_validation_rejects_tampering_and_extraneous_keys(self):
        good = snap(sample())
        validate_snapshot(good)
        tampered = json.loads(json.dumps(good))
        tampered["records"][0]["attributes"]["open_weights"] = False
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            validate_snapshot(tampered)
        extra = json.loads(json.dumps(good))
        extra["records"][0]["dangerous_future_column"] = "unhashed"
        with self.assertRaisesRegex(ValueError, "Unexpected discovery payload"):
            validate_snapshot(extra)

    def test_reject_missing_scope_or_empty_snapshots(self):
        with self.assertRaisesRegex(ValueError, "scope"):
            make_snapshot([sample()], scope={})
        with self.assertRaisesRegex(ValueError, "empty"):
            make_snapshot([], scope=SCOPE)

    def test_diff_added_not_observed_and_no_deletions(self):
        before = snap(sample(), sample(source_id="removed"))
        after = snap(sample(), sample(source_id="added"))
        result = compare_snapshots(before, after)
        self.assertEqual(len(result["added"]), 1)
        self.assertEqual(len(result["not_observed"]), 1)
        self.assertEqual(result["unchanged_count"], 1)
        self.assertIn("NOT a deletion instruction", result["note"])

    def test_scope_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "Different collection scopes"):
            compare_snapshots(snap(sample()), snap(sample(), scope={"models.dev": {"limit": 5}}))

    def test_pg_import_uses_transaction_copy_and_upsert_without_deletes(self):
        output = io.StringIO()
        emit_pg(snap(sample()), output)
        sql = output.getvalue()
        self.assertIn("BEGIN;", sql)
        self.assertIn("COPY _discovery_stage", sql)
        self.assertIn("ON CONFLICT (record_key) DO UPDATE SET", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotIn("DELETE FROM", sql)
        self.assertNotIn("DROP TABLE", sql)

    def test_pg_copy_rejects_multiline_external_name(self):
        with self.assertRaisesRegex(ValueError, "Multiline discovery field"):
            emit_pg(snap(replace(sample(), display_name="A\n\\.\nB")), io.StringIO())

    def test_surreal_import_has_required_option_and_stable_ids(self):
        record = sample()
        snapshot = snap(record)
        out1, out2 = io.StringIO(), io.StringIO()
        emit_surreal(snapshot, out1)
        emit_surreal(snapshot, out2)
        self.assertEqual(out1.getvalue(), out2.getvalue())
        self.assertTrue(out1.getvalue().startswith("OPTION IMPORT;"))
        self.assertIn(f"UPSERT discovery_cache:{snapshot['records'][0]['record_key']}", out1.getvalue())
        self.assertIn("RETURN NONE;", out1.getvalue())
        self.assertNotIn("DELETE", out1.getvalue())

    def test_modelsdev_collector_normalizes_real_toml_fields(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "models" / "org"
            folder.mkdir(parents=True)
            (folder / "alpha.toml").write_text(
                'name = "Alpha"\nopen_weights = true\ntool_call = false\n'
                '[limit]\ncontext = 4096\n', encoding="utf-8",
            )
            records = collect_modelsdev(Path(root), commit="a" * 40, limit=5)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].entity_type, "model_reference")
            self.assertEqual(records[0].source_id, "org/alpha")
            self.assertEqual(records[0].attributes["context_tokens"], 4096)
            self.assertIs(records[0].attributes["tools_supported"], False)
            self.assertIs(records[0].attributes["open_weights"], True)


if __name__ == "__main__":
    unittest.main()
