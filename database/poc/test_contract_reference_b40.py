"""B4.0: characterize B3.3 without changing any adapter or B2 behavior.

reference.b33.json was captured once using code archived from the published
B3.3 commit. Tests only READ these expected values; never regenerate them.
All fixtures are synthetic. No network, database, inference or GPU access.
"""

from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collect_discovery_snapshot import collect_modelsdev
from csghub_adapter import normalize_csghub_model
from discovery_cache import (
    canonical_json, compare_snapshots, make_snapshot, record_key, record_payload,
    validate_snapshot,
)
from emit_discovery_import import emit_pg, emit_surreal
from modelscope_adapter import normalize_modelscope_repo
from moark_adapter import select_moark_model
from source_adapters import (
    SourceRecord, normalize_awesome_agent, normalize_huggingface_model,
    normalize_nvidia_nim_metadata,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES = FIXTURES / "contracts_b40"
BASELINE_COMMIT = "d528580ddd6e1c4b364b64e2322eb2649e7b2e62"
CAPTURED_AT = "2026-10-27T00:00:00+00:00"
MODEL_COMMIT = "a" * 40
AGENTS_COMMIT = "5" * 40
NIM_RESOURCE = "nim/nvidia/parakeet-1-1b-rnnt-multilingual"
SOURCES = (
    "models.dev", "huggingface", "awesome-ai-agents", "nvidia-nim-metadata",
    "modelscope", "csghub", "moark",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def input_data(source):
    if source in ("huggingface", "awesome-ai-agents", "nvidia-nim-metadata"):
        return load_json(CASES / "inputs.synthetic.json")[source]
    filenames = {
        "modelscope": "modelscope_repoinfo.synthetic.json",
        "csghub": "csghub_model_info.synthetic.json",
        "moark": "moark_models.synthetic.json",
    }
    return load_json(FIXTURES / filenames[source])


def normalize(source, data=None, *, revision=None, source_root=CASES):
    if source == "models.dev":
        return collect_modelsdev(source_root, commit=revision or MODEL_COMMIT, limit=1)[0]
    if data is None:
        data = input_data(source)
    if source == "huggingface":
        return normalize_huggingface_model(data)
    if source == "awesome-ai-agents":
        return normalize_awesome_agent(data, source_commit=revision or AGENTS_COMMIT)
    if source == "nvidia-nim-metadata":
        return normalize_nvidia_nim_metadata(data, resource_id=NIM_RESOURCE, tag=revision or "1.5.0")
    if source == "modelscope":
        return normalize_modelscope_repo(data, requested_id="Qwen/Qwen3-0.6B")
    if source == "csghub":
        return normalize_csghub_model(data, requested_id="OpenCSG/csg-wukong-1B")
    if source == "moark":
        return select_moark_model(data, requested_id="Qwen3-8B")
    raise AssertionError("Unknown test source")


class ContractReferenceB40Tests(unittest.TestCase):
    def setUp(self):
        # Any accidental HTTP connection or DNS lookup fails, including when
        # a future refactor changes an otherwise pure normalizer.
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo"):
            guard = patch(target, side_effect=AssertionError("Network forbidden in B4.0 tests"))
            guard.start()
            self.addCleanup(guard.stop)
        self.reference = load_json(CASES / "reference.b33.json")

    def expected(self, source):
        return self.reference["sources"][source]["snapshot"]

    def scope(self, source):
        return deepcopy(self.expected(source)["scope"])

    def snapshot(self, source, record=None):
        return make_snapshot(
            [normalize(source) if record is None else record],
            scope=self.scope(source), captured_at=CAPTURED_AT,
        )

    def test_reference_is_a_literal_capture_from_published_b33(self):
        self.assertEqual(self.reference["baseline_commit"], BASELINE_COMMIT)
        self.assertIs(self.reference["synthetic"], True)
        self.assertEqual(set(self.reference["sources"]), set(SOURCES))
        self.assertEqual(len(self.reference["baseline_code_sha256"]), 8)

    def test_each_source_matches_full_frozen_record_and_snapshot(self):
        for source in SOURCES:
            with self.subTest(source=source):
                record = normalize(source)
                self.assertIsInstance(record, SourceRecord)
                self.assertIsInstance(record.relationships, tuple)
                expected = self.expected(source)
                # Compare the complete payload, not just its digest. Canonical
                # JSON also distinguishes false/0 and null/[] (Python == doesn't).
                entry = expected["records"][0]
                payload = {k: v for k, v in entry.items() if k not in ("record_key", "payload_sha256")}
                self.assertEqual(canonical_json(record_payload(record)), canonical_json(payload))
                self.assertEqual(record_key(record.source, record.entity_type, record.source_id), entry["record_key"])
                actual = self.snapshot(source, record)
                self.assertEqual(canonical_json(actual), canonical_json(expected))
                validate_snapshot(actual)

    def test_combined_snapshot_matches_frozen_identity_digest_and_order(self):
        expected = self.reference["combined"]
        snapshot = make_snapshot(
            [normalize(source) for source in reversed(SOURCES)],
            scope=deepcopy(expected["scope"]), captured_at=CAPTURED_AT,
        )
        self.assertEqual(snapshot["snapshot_id"], expected["snapshot_id"])
        self.assertEqual([r["record_key"] for r in snapshot["records"]], expected["ordered_record_keys"])
        entries = [self.expected(s)["records"][0] for s in SOURCES]
        self.assertEqual(canonical_json(snapshot["records"]), canonical_json(sorted(entries, key=lambda r: r["record_key"])))

    def test_revision_changes_preserve_each_source_identity(self):
        for source in SOURCES:
            with self.subTest(source=source):
                if source in ("models.dev", "awesome-ai-agents"):
                    changed = normalize(source, revision="b" * 40)
                elif source == "nvidia-nim-metadata":
                    changed = normalize(source, revision="1.6.0")
                else:
                    data = input_data(source)
                    if source == "moark":
                        # This API has NO model revision; creation time remains
                        # raw metadata, never an invented immutable revision.
                        data["data"][0]["created"] += 1
                    else:
                        data["sha"] = "b" * 40
                    changed = normalize(source, data)
                before = self.expected(source)["records"][0]
                after = self.snapshot(source, changed)["records"][0]
                self.assertEqual(after["record_key"], before["record_key"])
                self.assertNotEqual(after["payload_sha256"], before["payload_sha256"])
                if source == "moark":
                    self.assertIsNone(after["source_revision"])
                else:
                    self.assertNotEqual(after["source_revision"], before["source_revision"])

    def test_capture_time_changes_no_content_identity_or_digest(self):
        for source in SOURCES:
            with self.subTest(source=source):
                expected = self.expected(source)
                later = make_snapshot([normalize(source)], scope=self.scope(source), captured_at="2026-10-28T00:00:00Z")
                self.assertEqual(later["snapshot_id"], expected["snapshot_id"])
                self.assertEqual(canonical_json(later["records"]), canonical_json(expected["records"]))

    def test_null_false_zero_and_empty_collections_stay_distinct(self):
        nim = normalize("nvidia-nim-metadata").attributes
        self.assertIs(nim["tool_calling"], False)
        self.assertIs(type(nim["context_window"]), int)
        self.assertEqual(nim["context_window"], 0)
        self.assertIsNone(nim["profiles"][0]["precision"])
        self.assertEqual(nim["profiles"][0]["tested_gpu_devices"], [])
        absent = normalize("nvidia-nim-metadata", {}).attributes
        empty = normalize("nvidia-nim-metadata", {"profiles": []}).attributes
        self.assertIsNone(absent["profiles"])
        self.assertIsNone(absent["profiles_count"])
        self.assertEqual(empty["profiles"], [])
        self.assertIs(type(empty["profiles_count"]), int)
        self.assertEqual(empty["profiles_count"], 0)
        models = collect_modelsdev(CASES, commit=MODEL_COMMIT, limit=0)
        missing = models[1].attributes
        self.assertIsNone(missing["open_weights"])
        self.assertIsNone(missing["tools_supported"])
        self.assertEqual(missing["weights_count"], 0)
        self.assertIs(normalize("models.dev").attributes["tools_supported"], False)

    def test_absent_and_explicit_empty_fields_keep_source_specific_semantics(self):
        hf = normalize("huggingface", {"id": "example/model"}).attributes
        hf_empty = normalize("huggingface", {"id": "example/model", "siblings": [], "gated": False}).attributes
        self.assertEqual(hf["access"], "unknown")
        self.assertIsNone(hf["file_count"])
        self.assertIsNone(hf["base_models"])
        self.assertEqual(hf["available_formats"], [])
        self.assertEqual(hf_empty["file_count"], 0)
        self.assertEqual(hf_empty["access"], "public")
        for files, count, formats in ((None, None, None), ([], 0, [])):
            data = {"id": "OpenCSG/csg-wukong-1B", "siblings": files}
            attrs = normalize("csghub", data).attributes
            self.assertEqual(attrs["file_count"], count)
            self.assertEqual(attrs["observed_formats"], formats)
        absent = normalize("awesome-ai-agents", {"id": "x", "project": "X"}).attributes
        empty = normalize("awesome-ai-agents", {"id": "x", "project": "X", "sources": [], "has_public_repository": False}).attributes
        self.assertIsNone(absent["source_urls"])
        self.assertIsNone(absent["source_count"])
        self.assertIsNone(absent["has_public_repository"])
        self.assertEqual(empty["source_urls"], [])
        self.assertEqual(empty["source_count"], 0)
        self.assertIs(empty["has_public_repository"], False)

    def test_unknown_fields_preserved_raw_without_new_attributes_or_relationships(self):
        marker = {"nested": [None, False, 0, []]}
        for source in SOURCES:
            with self.subTest(source=source):
                if source == "models.dev":
                    with tempfile.TemporaryDirectory() as root:
                        folder = Path(root) / "models" / "example"
                        folder.mkdir(parents=True)
                        content = (CASES / "models/example/alpha.toml").read_text(encoding="utf-8")
                        (folder / "alpha.toml").write_text(content + '\n[b40_future]\nvalues = [0, 1]\n', encoding="utf-8")
                        record = normalize(source, source_root=Path(root))
                    self.assertEqual(record.raw_metadata["b40_future"], {"values": [0, 1]})
                else:
                    data = input_data(source)
                    target = data["data"][0] if source == "moark" else data
                    target["b40_future"] = deepcopy(marker)
                    record = normalize(source, data)
                    self.assertEqual(canonical_json(record.raw_metadata["b40_future"]), canonical_json(marker))
                self.assertNotIn("b40_future", record.attributes)
                expected = self.expected(source)["records"][0]
                self.assertEqual(record_key(record.source, record.entity_type, record.source_id), expected["record_key"])
                self.assertEqual(list(record.relationships), expected["relationships"])

    def test_same_name_and_id_do_not_merge_platforms_or_resource_types(self):
        # B2's namespace rules are independent of provider-specific ID syntax.
        records = [replace(normalize(s), source_id="shared/model", display_name="Same name") for s in SOURCES]
        snapshot = make_snapshot(records, scope=deepcopy(self.reference["combined"]["scope"]), captured_at=CAPTURED_AT)
        self.assertEqual(len(snapshot["records"]), 7)
        self.assertEqual(len({r["record_key"] for r in snapshot["records"]}), 7)
        self.assertEqual({r["entity_type"] for r in snapshot["records"]}, {
            "model_reference", "model_artifact", "agent_resource", "nim_microservice", "inference_endpoint",
        })
        self.assertEqual(len({record_key("one-source", kind, "shared/model") for kind in (
            "model_reference", "model_artifact", "agent_resource", "nim_microservice", "inference_endpoint",
        )}), 5)
        self.assertEqual(normalize("moark").attributes["access"], "unknown")
        self.assertIsNone(normalize("moark").attributes["weights_available"])

    def test_only_declared_hf_parent_relationship_is_present(self):
        record = normalize("huggingface")
        self.assertEqual(record.relationships, ({
            "relation": "declared_base_model", "source": "huggingface", "target_id": "google/gemma-3-1b-pt",
        },))
        self.assertNotEqual(record.source_id, record.relationships[0]["target_id"])
        for source in SOURCES:
            if source != "huggingface":
                with self.subTest(source=source):
                    self.assertEqual(normalize(source).relationships, ())

    def test_nim_tag_is_revision_not_identity_and_multitag_conflicts(self):
        first = normalize("nvidia-nim-metadata")
        other = normalize("nvidia-nim-metadata", revision="1.6.0")
        self.assertEqual(first.source_id, NIM_RESOURCE)
        self.assertEqual(other.source_id, NIM_RESOURCE)
        self.assertEqual(first.source_revision, "1.5.0")
        self.assertEqual(other.source_revision, "1.6.0")
        with self.assertRaisesRegex(ValueError, "Conflicting records"):
            make_snapshot([first, other], scope=self.scope("nvidia-nim-metadata"), captured_at=CAPTURED_AT)
        snapshot = make_snapshot([first, first], scope=self.scope("nvidia-nim-metadata"), captured_at=CAPTURED_AT)
        self.assertEqual(snapshot, self.expected("nvidia-nim-metadata"))

    def test_partial_observation_matches_frozen_comparison_without_deletion(self):
        combined = self.reference["combined"]
        records = [normalize(s) for s in SOURCES]
        before = make_snapshot(records, scope=deepcopy(combined["scope"]), captured_at=CAPTURED_AT)
        after = make_snapshot(records[:-1], scope=deepcopy(combined["scope"]), captured_at=CAPTURED_AT)
        self.assertEqual(after["snapshot_id"], self.reference["partial"]["snapshot_id"])
        self.assertEqual(compare_snapshots(before, after), self.reference["partial"]["comparison"])
        for emitter in (emit_pg, emit_surreal):
            out = io.StringIO()
            emitter(after, out)
            sql = out.getvalue()
            self.assertNotIn("DELETE", sql)
            self.assertNotIn("TRUNCATE", sql)
            self.assertNotIn("DROP TABLE", sql)
            self.assertNotIn("external_models", sql)
            self.assertNotIn(self.expected("moark")["records"][0]["record_key"], sql)

    def test_scope_changes_are_not_interpreted_as_missing_resources(self):
        original = self.snapshot("moark")
        altered_scope = self.scope("moark")
        altered_scope["moark"]["ids"] = ["other-selection"]
        different = make_snapshot([normalize("moark")], scope=altered_scope, captured_at=CAPTURED_AT)
        with self.assertRaisesRegex(ValueError, "Different collection scopes"):
            compare_snapshots(original, different)
        with self.assertRaisesRegex(ValueError, "empty"):
            make_snapshot([], scope=self.scope("moark"), captured_at=CAPTURED_AT)

    def test_read_only_consumers_do_not_mutate_snapshots_or_reference_file(self):
        reference_bytes = (CASES / "reference.b33.json").read_bytes()
        for source in SOURCES:
            with self.subTest(source=source):
                snapshot = self.snapshot(source)
                before = canonical_json(snapshot)
                validate_snapshot(snapshot)
                compare_snapshots(snapshot, deepcopy(snapshot))
                emit_pg(snapshot, io.StringIO())
                emit_surreal(snapshot, io.StringIO())
                self.assertEqual(canonical_json(snapshot), before)
        self.assertEqual((CASES / "reference.b33.json").read_bytes(), reference_bytes)

    def test_normalization_does_not_mutate_input_payloads_or_fixture_files(self):
        toml = CASES / "models/example/alpha.toml"
        before = toml.read_bytes()
        normalize("models.dev")
        self.assertEqual(toml.read_bytes(), before)
        for source in SOURCES[1:]:
            with self.subTest(source=source):
                data = input_data(source)
                before = canonical_json(data)
                normalize(source, data)
                self.assertEqual(canonical_json(data), before)

    def test_b41_defensive_copy_preserves_baseline_raw_values_without_aliasing(self):
        for source in SOURCES[1:]:
            with self.subTest(source=source):
                data = input_data(source)
                record = normalize(source, data)
                target = data["data"][0] if source == "moark" else data
                # Keep B3.3's ownership observations in the frozen file. B4.1
                # intentionally strengthens ownership, not serialized values.
                self.assertIn("raw_input_shared", self.reference["ownership"][source])
                self.assertIsNot(record.raw_metadata, target)
                target["b40_future"] = {"changed_after_normalization": True}
                self.assertNotIn("b40_future", record.raw_metadata)

    def test_b41_snapshot_copy_keeps_serialized_b33_reference_after_record_mutation(self):
        for source in SOURCES:
            with self.subTest(source=source):
                record = normalize(source)
                scope = self.scope(source)
                snapshot = make_snapshot([record], scope=scope, captured_at=CAPTURED_AT)
                entry = snapshot["records"][0]
                observed = self.reference["ownership"][source]
                self.assertTrue(observed["snapshot_attributes_shared"])
                self.assertTrue(observed["snapshot_raw_shared"])
                self.assertTrue(observed["snapshot_scope_shared"])
                self.assertIsNot(entry["attributes"], record.attributes)
                self.assertIsNot(entry["raw_metadata"], record.raw_metadata)
                self.assertIsNot(snapshot["scope"], scope)
                # Serializing then loading detaches a persisted observation.
                persisted = json.loads(canonical_json(snapshot))
                record.attributes["b40_future"] = [False, 0]
                validate_snapshot(snapshot)
                self.assertEqual(snapshot, self.expected(source))
                self.assertEqual(persisted, self.expected(source))
                validate_snapshot(persisted)


if __name__ == "__main__":
    unittest.main()
