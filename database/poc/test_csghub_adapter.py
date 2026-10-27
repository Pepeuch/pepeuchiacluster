"""B3.2 CSGHub contracts run entirely offline; never download model files."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from csghub_adapter import model_id, normalize_csghub_model
from discovery_cache import make_snapshot, record_key, validate_snapshot
from probe_csghub import OFFICIAL_ENDPOINT, read_online


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "csghub_model_info.synthetic.json"
MODEL = "OpenCSG/csg-wukong-1B"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class CSGHubContractTests(unittest.TestCase):
    def test_identity_revision_and_isolated_namespace(self):
        record = normalize_csghub_model(fixture(), requested_id=MODEL)
        self.assertEqual((record.source, record.entity_type, record.source_id),
                         ("csghub", "model_artifact", MODEL))
        self.assertEqual(record.source_revision, "a" * 40)
        self.assertNotEqual(record_key("csghub", "model_artifact", MODEL),
                            record_key("huggingface", "model_artifact", MODEL))
        self.assertNotEqual(record_key("csghub", "model_artifact", MODEL),
                            record_key("modelscope", "model_artifact", MODEL))
        validate_snapshot(make_snapshot([record], scope={"csghub": {"ids": [MODEL]}}))

    def test_missing_gating_is_unknown_not_public_download_permission(self):
        record = normalize_csghub_model(fixture(), requested_id=MODEL)
        self.assertEqual(record.attributes["visibility"], "public")
        self.assertEqual(record.attributes["access"], "unknown")
        self.assertIsNone(record.attributes["gated"])
        self.assertIsNone(record.attributes["approval_mode"])

    def test_explicit_gating_and_private(self):
        data = fixture()
        data["gated"] = "manual"
        record = normalize_csghub_model(data, requested_id=MODEL)
        self.assertEqual(record.attributes["access"], "gated")
        self.assertEqual(record.attributes["approval_mode"], "manual")
        data["private"] = True
        self.assertEqual(normalize_csghub_model(data, requested_id=MODEL).attributes["access"], "private")
        data["private"] = False
        data["gated"] = False
        self.assertEqual(normalize_csghub_model(data, requested_id=MODEL).attributes["access"], "public")
        data["gated"] = "invalid"
        with self.assertRaisesRegex(ValueError, "gated"):
            normalize_csghub_model(data, requested_id=MODEL)

    def test_unknown_privacy_and_missing_files_stay_unknown(self):
        data = fixture()
        data.pop("private")
        data.pop("siblings")
        record = normalize_csghub_model(data, requested_id=MODEL)
        self.assertEqual(record.attributes["visibility"], "unknown")
        self.assertEqual(record.attributes["access"], "unknown")
        self.assertIsNone(record.attributes["file_count"])
        self.assertIsNone(record.attributes["observed_formats"])

    def test_explicit_empty_file_list_is_distinct_from_unknown(self):
        data = fixture()
        data["siblings"] = []
        record = normalize_csghub_model(data, requested_id=MODEL)
        self.assertEqual(record.attributes["file_count"], 0)
        self.assertEqual(record.attributes["observed_formats"], [])

    def test_observed_formats_only_from_actual_files(self):
        record = normalize_csghub_model(fixture(), requested_id=MODEL)
        self.assertEqual(record.attributes["observed_formats"], ["safetensors"])
        self.assertEqual(record.attributes["file_count"], 2)
        data = fixture()
        data["siblings"].append({"rfilename": "quant/model-q4.gguf"})
        self.assertEqual(normalize_csghub_model(data, requested_id=MODEL).attributes["observed_formats"],
                         ["gguf", "safetensors"])

    def test_license_tag_is_not_declared_license(self):
        record = normalize_csghub_model(fixture(), requested_id=MODEL)
        self.assertIsNone(record.attributes["license"])
        data = fixture()
        data["cardData"] = {"license": "apache-2.0"}
        self.assertEqual(normalize_csghub_model(data, requested_id=MODEL).attributes["license"], "apache-2.0")
        data["license"] = "mit"
        with self.assertRaisesRegex(ValueError, "Conflicting CSGHub license"):
            normalize_csghub_model(data, requested_id=MODEL)
        data["cardData"].pop("license")
        self.assertEqual(normalize_csghub_model(data, requested_id=MODEL).attributes["license"], "mit")

    def test_invalid_id_or_non_model_payload_rejected(self):
        for invalid in ("bare", "foo/bar/baz", "../x", "foo/..", "foo/bad?x", "foo/evil name"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                model_id(invalid)
        data = fixture()
        data["id"] = "Other/model"
        with self.assertRaisesRegex(ValueError, "differs"):
            normalize_csghub_model(data, requested_id=MODEL)
        data = fixture()
        data["repo_type"] = "dataset"
        with self.assertRaisesRegex(ValueError, "not a model"):
            normalize_csghub_model(data, requested_id=MODEL)

    def test_counts_boolean_tags_and_siblings_fail_closed(self):
        data = fixture()
        for field, value in (("downloads", True), ("likes", -1), ("tags", [""]),
                             ("siblings", ["model.safetensors"]), ("private", "no")):
            with self.subTest(field=field):
                bad = deepcopy(data)
                bad[field] = value
                with self.assertRaises(ValueError):
                    normalize_csghub_model(bad, requested_id=MODEL)

    def test_short_sha_not_revision_but_preserved_raw(self):
        data = fixture()
        data["sha"] = "a1b2c3"
        record = normalize_csghub_model(data, requested_id=MODEL)
        self.assertIsNone(record.source_revision)
        self.assertEqual(record.raw_metadata["sha"], "a1b2c3")

    def test_credentials_and_nan_rejected_before_snapshot(self):
        data = fixture()
        data["nested"] = {"access_token": "do-not-persist"}
        with self.assertRaisesRegex(ValueError, "credential-like"):
            normalize_csghub_model(data, requested_id=MODEL)
        data = fixture()
        data["downloads"] = float("nan")
        with self.assertRaises(ValueError):
            normalize_csghub_model(data, requested_id=MODEL)

    def test_fixture_cli_stdout_is_valid_snapshot(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "probe_csghub.py"),
             "--fixture", str(FIXTURE), "--model-id", MODEL],
            capture_output=True, text=True, check=True,
        )
        snapshot = json.loads(result.stdout)
        validate_snapshot(snapshot)
        self.assertEqual(len(snapshot["records"]), 1)
        self.assertEqual(snapshot["records"][0]["source"], "csghub")
        self.assertEqual(snapshot["scope"]["csghub"]["endpoint"], OFFICIAL_ENDPOINT)

    def test_online_uses_only_bounded_public_metadata_get(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, n):
                self.limit = n
                return json.dumps(fixture()).encode("utf-8")

        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        with patch("probe_csghub.build_opener", return_value=opener) as build:
            data = read_online(MODEL)
        self.assertEqual(data["id"], MODEL)
        self.assertEqual(opener.request.full_url,
                         "https://hub.opencsg.com/csg/api/models/OpenCSG/csg-wukong-1B/revision/main")
        self.assertEqual(opener.request.get_method(), "GET")
        self.assertEqual(opener.timeout, 20)
        self.assertNotIn("Authorization", opener.request.headers)
        self.assertEqual(build.call_count, 1)

    def test_online_response_size_limit(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, n):
                return b"x" * n

        class Opener:
            def open(self, request, timeout):
                return Response()

        with patch("probe_csghub.build_opener", return_value=Opener()):
            with self.assertRaisesRegex(ValueError, "size limit"):
                read_online(MODEL)


if __name__ == "__main__":
    unittest.main()
