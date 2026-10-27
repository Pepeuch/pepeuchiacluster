"""B4.1: JSON/type/ownership hardening, with unchanged B3.3 payloads."""

from datetime import datetime, timezone
from enum import Enum
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from discovery_cache import canonical_json, make_snapshot, validate_snapshot
from metadata_primitives import (
    assert_secret_free, copy_metadata, error_summary, nonempty_string,
    object_value, optional_nonnegative_int, strict_json_loads,
)
from source_adapters import SourceRecord
from test_contract_reference_b40 import CAPTURED_AT, SOURCES, input_data, normalize


class MetadataPrimitiveTests(unittest.TestCase):
    def test_identical_type_rules_preserve_values_without_coercion(self):
        data = {"x": [None, False, 0, []]}
        self.assertIs(object_value(data, "field"), data)
        self.assertEqual(nonempty_string(" padded ", "field"), " padded ")
        for value in (None, False, [], "value"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                object_value(value, "field")
        for value in (None, False, 0, "", " \n"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                nonempty_string(value, "field")
        self.assertIsNone(optional_nonnegative_int(None, "field"))
        self.assertEqual(optional_nonnegative_int(0, "field"), 0)
        for value in (False, True, -1, 1.5, "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                optional_nonnegative_int(value, "field")

    def test_json_copy_preserves_nested_unknowns_and_detaches_inputs(self):
        data = {"future": [None, False, 0, [], {"text": "é"}]}
        result = copy_metadata(data)
        self.assertEqual(canonical_json(result), canonical_json(data))
        self.assertIsNot(result["future"], data["future"])
        data["future"][-1]["text"] = "changed"
        self.assertEqual(result["future"][-1]["text"], "é")

    def test_recursive_secrets_rejected_without_key_or_value_in_error(self):
        for key in ("api_key", "API-Key", "accessToken", "Authorization", "Cookie", "Set-Cookie",
                    "private_key", "refresh_token", "client_secret", "X-API-Key"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError) as caught:
                    copy_metadata({"future": [{key: "SYNTHETIC-DO-NOT-USE"}]})
                self.assertNotIn(key, str(caught.exception))
                self.assertNotIn("SYNTHETIC-DO-NOT-USE", str(caught.exception))
        # Counts, capabilities and tokenizers are ordinary metadata.
        assert_secret_free({"max_tokens": 0, "token_count": 12, "tokenizer": "test"})

    def test_nonstring_keys_cycles_and_nonfinite_numbers_rejected(self):
        recursive = []
        recursive.append(recursive)
        for value in ({0: "key"}, {"x": float("nan")}, {"x": float("inf")}, recursive):
            with self.subTest(kind=type(value).__name__), self.assertRaises((ValueError, TypeError)):
                copy_metadata(value)

    def test_sdk_conversion_is_explicit_and_post_conversion_checked(self):
        class Visibility(Enum):
            PUBLIC = 5

        data = {"visibility": Visibility.PUBLIC, "modified": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        def convert(value):
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, datetime):
                return value.isoformat()
            raise TypeError("Unsupported SDK metadata")
        self.assertEqual(copy_metadata(data, default=convert), {
            "visibility": 5, "modified": "2026-01-01T00:00:00+00:00",
        })
        class Custom:
            pass
        with self.assertRaises(ValueError):
            copy_metadata({"value": Custom()}, default=lambda _: {"api_key": "SYNTHETIC"})
        with self.assertRaises(TypeError):
            copy_metadata({"value": Custom()})

    def test_strict_json_rejects_ambiguous_and_malformed_responses(self):
        for payload in ('{"id":"one","id":"two"}', '{"nested":{"x":0,"x":false}}',
                        '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}',
                        '{"x":', '{}{}', b'\xff'):
            with self.subTest(payload=payload), self.assertRaises((ValueError, UnicodeError)):
                strict_json_loads(payload)
        self.assertEqual(strict_json_loads(b'{"x":[null,false,0,[]]}'), {"x": [None, False, 0, []]})
        self.assertEqual(strict_json_loads('{"x":0,"X":1}'), {"x": 0, "X": 1})

    def test_safe_error_summary_never_formats_exception_content(self):
        class Sensitive(ValueError):
            def __str__(self):
                raise AssertionError("Exception content must not be formatted")
        self.assertIn("Sensitive", error_summary("Fixture", Sensitive()))
        error = HTTPError("https://example.test/?credential=SYNTHETIC", 429, "SYNTHETIC BODY", {}, None)
        summary = error_summary("Fixture", error)
        self.assertIn("HTTP 429", summary)
        self.assertNotIn("SYNTHETIC", summary)
        self.assertNotIn("example.test", summary)


class MetadataIntegrationTests(unittest.TestCase):
    def test_record_constructor_owns_attributes_relations_and_raw_metadata(self):
        attributes = {"unknown": [None, False, 0, []]}
        relationships = ({"relation": "declared", "source": "fixture", "target_id": "parent"},)
        raw = {"nested": {"items": []}}
        record = SourceRecord("fixture", "id", None, "model_artifact", "Name", attributes, relationships, raw)
        before = canonical_json({"a": record.attributes, "r": record.relationships, "raw": record.raw_metadata})
        attributes["unknown"].append(True)
        relationships[0]["target_id"] = "changed"
        raw["nested"]["items"].append("changed")
        self.assertEqual(canonical_json({"a": record.attributes, "r": record.relationships, "raw": record.raw_metadata}), before)

    def test_all_source_records_reject_nested_credentials(self):
        for source in SOURCES:
            with self.subTest(source=source):
                record = normalize(source)
                raw = dict(record.raw_metadata)
                raw["future"] = [{"accessToken": "SYNTHETIC-DO-NOT-USE"}]
                with self.assertRaises(ValueError):
                    SourceRecord(
                        record.source, record.source_id, record.source_revision, record.entity_type,
                        record.display_name, record.attributes, record.relationships, raw,
                    )

    def test_all_record_data_and_snapshot_scope_are_defensive_copies(self):
        for source in SOURCES:
            with self.subTest(source=source):
                record = normalize(source)
                scope = {source: {"ids": [record.source_id]}}
                snapshot = make_snapshot([record], scope=scope, captured_at=CAPTURED_AT)
                before = canonical_json(snapshot)
                record.attributes["later"] = {"values": [False, 0]}
                record.raw_metadata["later"] = []
                scope[source]["ids"].append("later")
                if record.relationships:
                    record.relationships[0]["target_id"] = "later"
                self.assertEqual(canonical_json(snapshot), before)
                validate_snapshot(snapshot)

    def test_b1_and_b3_normalizers_reject_secrets_in_unknown_raw_fields(self):
        for source in SOURCES[1:]:
            with self.subTest(source=source):
                data = input_data(source)
                target = data["data"][0] if source == "moark" else data
                target["nested"] = [{"privateKey": "SYNTHETIC-DO-NOT-USE"}]
                with self.assertRaises(ValueError):
                    normalize(source, data)

    def test_cli_diagnostics_do_not_echo_sensitive_exceptions(self):
        from collect_discovery_snapshot import main
        with patch("sys.argv", ["collect_discovery_snapshot.py"]), \
                patch("collect_discovery_snapshot.source_commit", side_effect=ValueError("SYNTHETIC-sensitive-detail")), \
                patch("sys.stdout", new_callable=io.StringIO) as out, \
                patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(main(), 1)
            self.assertEqual(out.getvalue(), "")
            self.assertNotIn("SYNTHETIC", err.getvalue())

    def test_probe_fixture_rejects_duplicate_json_keys_before_snapshot_output(self):
        from probe_csghub import main
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ambiguous.json"
            path.write_text('{"id":"wrong","id":"OpenCSG/csg-wukong-1B"}', encoding="utf-8")
            with patch("sys.argv", ["probe_csghub.py", "--fixture", str(path)]), \
                    patch("sys.stdout", new_callable=io.StringIO) as out, \
                    patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(main(), 1)
                self.assertEqual(out.getvalue(), "")

    def test_import_file_rejects_duplicate_keys_before_any_sql_output(self):
        from emit_discovery_import import main
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ambiguous.json"
            path.write_text('{"format":"wrong","format":"pepeuch-ai.discovery-cache/v1"}', encoding="utf-8")
            with patch("sys.argv", ["emit_discovery_import.py", "--engine", "pg", "--snapshot", str(path)]), \
                    patch("sys.stdout", new_callable=io.StringIO) as out, \
                    patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(main(), 1)
                self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
