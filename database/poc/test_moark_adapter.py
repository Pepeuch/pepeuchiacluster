"""MoArk contracts and probe failure paths; all tests are offline."""

from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from discovery_cache import make_snapshot, record_key, validate_snapshot
from emit_discovery_import import emit_pg, emit_surreal
from moark_adapter import API_BASE, CATALOG_URL, model_id, normalize_moark_model, select_moark_model
from probe_moark import MAX_METADATA_BYTES, _NoRedirect, main, read_online


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "moark_models.synthetic.json"
MODEL = "Qwen3-8B"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class Response:
    def __init__(self, payload):
        self.payload = payload
        self.read_limit = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, n):
        self.read_limit = n
        return self.payload[:n]


class MoArkContractTests(unittest.TestCase):
    def test_endpoint_identity_is_separate_from_hubs_and_weights(self):
        record = select_moark_model(fixture(), requested_id=MODEL)
        self.assertEqual((record.source, record.entity_type, record.source_id),
                         ("moark", "inference_endpoint", MODEL))
        for source, entity in (("huggingface", "model_artifact"), ("csghub", "model_artifact"),
                               ("modelscope", "model_artifact"), ("moark", "model_artifact")):
            self.assertNotEqual(record_key(record.source, record.entity_type, MODEL),
                                record_key(source, entity, MODEL))
        self.assertEqual(record.relationships, ())
        self.assertEqual(record.attributes["api_base"], API_BASE)
        self.assertEqual(record.attributes["catalog_url"], CATALOG_URL)

    def test_created_and_owner_do_not_establish_revision_or_rights(self):
        record = select_moark_model(fixture(), requested_id=MODEL)
        self.assertIsNone(record.source_revision)
        self.assertEqual(record.attributes["created"], 1700000000)
        self.assertEqual(record.attributes["access"], "unknown")
        self.assertIsNone(record.attributes["license"])
        self.assertIsNone(record.attributes["weights_available"])

    def test_absent_optional_metadata_remains_unknown(self):
        record = normalize_moark_model({"id": MODEL, "object": "model"}, requested_id=MODEL)
        self.assertIsNone(record.attributes["created"])
        self.assertIsNone(record.attributes["owned_by"])

    def test_raw_metadata_copied_without_interpreting_unknown_details(self):
        data = fixture()
        data["data"][0]["operations"] = [{"path": "/chat/completions", "price": "0.00000000"}]
        data["data"][0]["upstream_name"] = "Qwen/Qwen3-8B"
        record = select_moark_model(data, requested_id=MODEL)
        self.assertEqual(record.raw_metadata, data["data"][0])
        self.assertEqual(record.relationships, ())
        self.assertEqual(record.attributes["access"], "unknown")
        data["data"][0]["operations"].clear()
        self.assertEqual(len(record.raw_metadata["operations"]), 1)

    def test_reject_invalid_ids_before_network(self):
        for value in (None, "", "../x", "foo/..", "foo//bar", "x?token=y", "x\ny", "x#y", " x", "x" * 257):
            with self.subTest(value=value), patch("probe_moark.build_opener") as build:
                with self.assertRaises(ValueError):
                    read_online(value)
                build.assert_not_called()
        self.assertEqual(model_id("vendor/model-v1.0"), "vendor/model-v1.0")

    def test_missing_id_is_not_a_claim_of_removal(self):
        with self.assertRaisesRegex(ValueError, "not observed"):
            select_moark_model(fixture(), requested_id="Qwen3-8")

    def test_duplicate_ids_fail_even_if_identical_or_unselected(self):
        for index in (0, 1):
            for conflicting in (False, True):
                data = fixture()
                extra = deepcopy(data["data"][index])
                if conflicting:
                    extra["created"] = 123
                data["data"].append(extra)
                with self.assertRaisesRegex(ValueError, "Duplicate"):
                    select_moark_model(data, requested_id=MODEL)

    def test_invalid_envelopes_pagination_and_nonmodels_fail(self):
        for data in ([], {}, {"object": "list", "data": {}},
                     {"object": "list", "data": [None]},
                     {"object": "list", "data": [{"id": MODEL, "object": "dataset"}]},
                     {**fixture(), "has_more": True}, {**fixture(), "has_more": 0},
                     {**fixture(), "next": "cursor"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                select_moark_model(data, requested_id=MODEL)

    def test_invalid_optional_types_and_identity_fail(self):
        for field, value in (("created", True), ("created", -1), ("created", "123"),
                             ("owned_by", False), ("owned_by", ""), ("id", "other")):
            data = fixture()["data"][0]
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                normalize_moark_model(data, requested_id=MODEL)

    def test_credentials_and_nonfinite_metadata_fail_anywhere_in_roster(self):
        for value in ({"Access-Token": "do-not-persist"}, {"Cookie": "secret"},
                      {"price": float("nan")}, {"price": float("inf")}):
            data = fixture()
            data["data"][1]["extra"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_moark_model(data, requested_id=MODEL)

    def test_snapshot_determinism_and_both_import_generators(self):
        record = select_moark_model(fixture(), requested_id=MODEL)
        scope = {"moark": {"ids": [MODEL], "input": "synthetic_fixture"}}
        first = make_snapshot([record], scope=scope, captured_at="2026-10-27T10:00:00Z")
        second = make_snapshot([record], scope=scope, captured_at="2026-10-27T11:00:00Z")
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        validate_snapshot(first)
        pg, surreal = io.StringIO(), io.StringIO()
        emit_pg(first, pg)
        emit_surreal(first, surreal)
        self.assertIn("ON CONFLICT (record_key) DO UPDATE", pg.getvalue())
        self.assertIn("inference_endpoint", pg.getvalue())
        self.assertIn("UPSERT discovery_cache:" + first["records"][0]["record_key"], surreal.getvalue())
        self.assertNotIn("external_models", pg.getvalue() + surreal.getvalue())

    def test_cli_fixture_valid_and_failed_selection_has_empty_stdout(self):
        command = [sys.executable, str(ROOT / "probe_moark.py"), "--fixture", str(FIXTURE)]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        snapshot = json.loads(result.stdout)
        validate_snapshot(snapshot)
        self.assertEqual(len(snapshot["records"]), 1)
        self.assertEqual(snapshot["scope"]["moark"]["input"], "synthetic_fixture")
        result = subprocess.run(command + ["--model-id", "missing"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_online_single_anonymous_bounded_get(self):
        response = Response(json.dumps(fixture()).encode())
        with patch("probe_moark.build_opener") as build:
            build.return_value.open.return_value = response
            self.assertEqual(read_online(MODEL), fixture())
        build.assert_called_once()
        self.assertIsInstance(build.call_args.args[0], _NoRedirect)
        build.return_value.open.assert_called_once()
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, CATALOG_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("Cookie", request.headers)
        self.assertEqual(build.return_value.open.call_args.kwargs["timeout"], 20)
        self.assertEqual(response.read_limit, MAX_METADATA_BYTES + 1)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.test"))

    def test_online_oversize_invalid_json_and_wrong_root_fail(self):
        for payload in (b"x" * (MAX_METADATA_BYTES + 1), b"<html>no</html>", b"[]"):
            with self.subTest(length=len(payload)), patch("probe_moark.build_opener") as build:
                build.return_value.open.return_value = Response(payload)
                with self.assertRaises(ValueError):
                    read_online(MODEL)

    def test_http_refusals_stop_without_retry_or_error_body_in_logs(self):
        for status in (301, 401, 403, 429, 500):
            error = HTTPError(CATALOG_URL, status, "sensitive body", {}, None)
            with self.subTest(status=status), patch("probe_moark.build_opener") as build:
                build.return_value.open.side_effect = error
                with patch.object(sys, "argv", ["probe_moark.py", "--online"]), \
                        patch("sys.stdout", new_callable=io.StringIO) as out, \
                        patch("sys.stderr", new_callable=io.StringIO) as err:
                    self.assertEqual(main(), 1)
                    self.assertEqual(out.getvalue(), "")
                    self.assertNotIn("sensitive body", err.getvalue())
                    self.assertIn(f"HTTP {status}", err.getvalue())
                build.return_value.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
