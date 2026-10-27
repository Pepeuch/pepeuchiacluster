"""B3.1 ModelScope fixture tests; the test suite never connects to ModelScope."""

from copy import deepcopy
from datetime import datetime, timezone
from enum import IntEnum
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from discovery_cache import make_snapshot, record_key, validate_snapshot
from modelscope_adapter import normalize_modelscope_repo
from probe_modelscope import read_online


MODEL_ID = "Qwen/Qwen3-0.6B"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "modelscope_repoinfo.synthetic.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class ModelScopeContractTests(unittest.TestCase):
    def test_repodata_is_model_artifact_with_separate_identity(self):
        normalized = normalize_modelscope_repo(fixture(), requested_id=MODEL_ID)
        self.assertEqual(normalized.source, "modelscope")
        self.assertEqual(normalized.source_id, MODEL_ID)
        self.assertEqual(normalized.entity_type, "model_artifact")
        self.assertEqual(normalized.source_revision, None)
        self.assertEqual(normalized.attributes["access"], "public")
        self.assertIs(normalized.attributes["gated"], False)
        self.assertEqual(normalized.attributes["files"], None)
        self.assertEqual(normalized.relationships, ())
        self.assertNotEqual(record_key("modelscope", "model_artifact", MODEL_ID),
                            record_key("huggingface", "model_artifact", MODEL_ID))
        validate_snapshot(make_snapshot([normalized], scope={"modelscope": {"ids": [MODEL_ID]}}))

    def test_visibility_null_is_unknown_not_public(self):
        data = fixture()
        data.pop("visibility")
        data.pop("gated")
        record = normalize_modelscope_repo(data, requested_id=MODEL_ID)
        self.assertEqual(record.attributes["access"], "unknown")
        self.assertIsNone(record.attributes["gated"])

    def test_visibility_intenum_internal_and_private_are_separate(self):
        data = fixture()
        data["visibility"] = 3
        self.assertEqual(normalize_modelscope_repo(data, requested_id=MODEL_ID).attributes["access"], "internal")
        data["visibility"] = "private"
        self.assertEqual(normalize_modelscope_repo(data, requested_id=MODEL_ID).attributes["access"], "private")

    def test_explicit_gated_true_and_contradictory_public_rejected(self):
        data = fixture()
        data["visibility"] = 1
        data["gated"] = True
        self.assertEqual(normalize_modelscope_repo(data, requested_id=MODEL_ID).attributes["access"], "gated")
        data["visibility"] = 5
        with self.assertRaisesRegex(ValueError, "Conflicting public and gated"):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)

    def test_private_and_visibility_contradiction_is_rejected(self):
        data = fixture()
        data["private"] = True
        with self.assertRaisesRegex(ValueError, "Conflicting ModelScope private"):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)

    def test_identity_verified_numeric_database_id_not_identity(self):
        data = fixture()
        data.pop("repo_id")
        data["id"] = 12345
        self.assertEqual(normalize_modelscope_repo(data, requested_id=MODEL_ID).source_id, MODEL_ID)
        data["owner"] = "OtherOwner"
        with self.assertRaisesRegex(ValueError, "does not match"):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)

    def test_malformed_identity_or_wrong_repository_type_rejected(self):
        data = fixture()
        data["repo_type"] = "dataset"
        with self.assertRaisesRegex(ValueError, "not a model"):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)
        with self.assertRaisesRegex(ValueError, "owner/name"):
            normalize_modelscope_repo(fixture(), requested_id="not-an-owner-name")
        data = fixture()
        data["repo_id"] = "Qwen/../bad"
        with self.assertRaises(ValueError):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)

    def test_optional_invalid_counts_and_tags_rejected(self):
        data = fixture()
        data["downloads"] = True
        with self.assertRaisesRegex(ValueError, "downloads"):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)
        data = fixture()
        data["tags"] = ["", "abc"]
        with self.assertRaisesRegex(ValueError, "tags"):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)

    def test_empty_optional_strings_are_unknown_and_epoch_is_kept(self):
        data = fixture()
        data["description"] = ""
        data["license"] = "  "
        data["last_modified"] = 1770000000
        record = normalize_modelscope_repo(data, requested_id=MODEL_ID)
        self.assertIsNone(record.attributes["description"])
        self.assertIsNone(record.attributes["license"])
        self.assertEqual(record.attributes["last_modified"], 1770000000)

    def test_sdk_enum_datetime_are_json_normalized(self):
        class Visibility(IntEnum):
            PUBLIC = 5

        data = fixture()
        data["visibility"] = Visibility.PUBLIC
        data["last_modified"] = datetime(2026, 10, 27, tzinfo=timezone.utc)
        record = normalize_modelscope_repo(data, requested_id=MODEL_ID)
        self.assertEqual(record.attributes["visibility"], "public")
        self.assertEqual(record.attributes["last_modified"], "2026-10-27T00:00:00+00:00")

    def test_commit_must_be_full_and_explicit(self):
        data = fixture()
        data["sha"] = "a" * 40
        data["revision"] = "master"
        record = normalize_modelscope_repo(data, requested_id=MODEL_ID)
        self.assertEqual(record.source_revision, "a" * 40)
        self.assertEqual(record.attributes["revision_label"], "master")
        data["sha"] = "abcdef0"  # Not an immutable full commit.
        self.assertIsNone(normalize_modelscope_repo(data, requested_id=MODEL_ID).source_revision)

    def test_reject_credential_like_raw_metadata(self):
        data = fixture()
        data["extra"] = {"api_token": "SHOULD-NOT-BE-SAVED"}
        with self.assertRaisesRegex(ValueError, "credential-like"):
            normalize_modelscope_repo(data, requested_id=MODEL_ID)

    def test_fixture_cli_generates_snapshot_without_sdk(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "probe_modelscope.py"),
             "--fixture", str(FIXTURE), "--model-id", MODEL_ID],
            capture_output=True, text=True, check=True,
        )
        snapshot = json.loads(result.stdout)
        validate_snapshot(snapshot)
        self.assertEqual(len(snapshot["records"]), 1)
        self.assertEqual(snapshot["records"][0]["source"], "modelscope")
        self.assertIn("Prepared 1 ModelScope record", result.stderr)

    def test_online_uses_metadata_only_sdk_method(self):
        class FakeRepo:
            def to_dict(self):
                return deepcopy(fixture())

        class FakeApi:
            def __init__(self, *, endpoint):
                self.endpoint = endpoint

            def get_repo(self, repo_id, *, repo_type):
                self.test_inputs = (repo_id, repo_type)
                return FakeRepo()

        import types
        with patch.dict(sys.modules, {"modelscope_hub": types.SimpleNamespace(HubApi=FakeApi)}):
            data = read_online(MODEL_ID, "https://modelscope.cn")
        self.assertEqual(data["repo_id"], MODEL_ID)


if __name__ == "__main__":
    unittest.main()
