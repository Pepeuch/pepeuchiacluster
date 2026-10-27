"""Manual registry/CLI integration on fixtures only, against literal B3.3 data."""

from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from discovery_cache import canonical_json, validate_snapshot
from discovery_registry import DEFAULT_MANIFEST, FIXTURE_BINDINGS, FixtureSelection, discover_fixtures
from discover_sources import main
from source_spec_design import SOURCE_SPECS


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def guarded_cli(script, *args, deny_adapters=False):
    """A fresh process catches accidental network/SDK/DB/subprocess activity."""
    blocked = ["modelscope_hub", "huggingface_hub", "pycsghub", "psycopg", "psycopg2", "surrealdb"]
    if deny_adapters:
        blocked.extend(["source_adapters", "collect_discovery_snapshot", "moark_adapter", "modelscope_adapter", "csghub_adapter"])
    code = '''
import builtins, json, runpy, sys
blocked = set(json.loads(sys.argv[1]))
script = sys.argv[2]
sys.path.insert(0, sys.argv[3])
sys.argv = [script, *sys.argv[4:]]
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Forbidden optional dependency or eager adapter import')
    return original(name, *args, **kwargs)
def audit(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen'):
        raise AssertionError('Forbidden network or subprocess action')
    if event == 'open' and str(args[0]).endswith('reference.b33.json'):
        raise AssertionError('Runtime must not read expected test outputs')
builtins.__import__ = guarded
sys.addaudithook(audit)
runpy.run_path(script, run_name='__main__')
'''
    return subprocess.run([sys.executable, "-I", "-c", code, json.dumps(blocked), str(ROOT / script), str(ROOT), *args],
                          capture_output=True, text=True)


class DiscoveryRegistryTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo"):
            guard = patch(target, side_effect=AssertionError("Network forbidden in registry tests"))
            guard.start()
            self.addCleanup(guard.stop)
        self.reference = json.loads((FIXTURES / "contracts_b40/reference.b33.json").read_text())

    def temporary_manifest(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name) / "fixtures"
        shutil.copytree(FIXTURES, root)
        path = root / DEFAULT_MANIFEST.name
        return path, json.loads(path.read_text())

    def test_registry_connects_every_source_to_its_existing_spec(self):
        self.assertEqual(set(FIXTURE_BINDINGS), set(SOURCE_SPECS))
        for source, binding in FIXTURE_BINDINGS.items():
            with self.subTest(source=source):
                self.assertIs(binding.spec, SOURCE_SPECS[source])
                self.assertTrue(callable(binding.normalize_fixture))
        with self.assertRaises(TypeError):
            FIXTURE_BINDINGS["extra"] = FIXTURE_BINDINGS["moark"]

    def test_seven_individual_snapshots_equal_frozen_b33_data(self):
        for source in FIXTURE_BINDINGS:
            with self.subTest(source=source):
                snapshot = discover_fixtures(sources=[source])
                expected = self.reference["sources"][source]["snapshot"]
                self.assertEqual(canonical_json(snapshot), canonical_json(expected))
                validate_snapshot(snapshot)

    def test_combined_snapshot_and_every_digest_match_the_frozen_b33_reference(self):
        actual = discover_fixtures()
        expected = {
            "format": "pepeuch-ai.discovery-cache/v1",
            "captured_at": self.reference["captured_at"],
            "scope": self.reference["combined"]["scope"],
            "snapshot_id": self.reference["combined"]["snapshot_id"],
            "records": sorted([entry["snapshot"]["records"][0] for entry in self.reference["sources"].values()],
                              key=lambda record: record["record_key"]),
        }
        self.assertEqual(canonical_json(actual), canonical_json(expected))
        self.assertEqual([record["record_key"] for record in actual["records"]], self.reference["combined"]["ordered_record_keys"])

    def test_order_of_requested_sources_does_not_change_snapshot(self):
        forward = discover_fixtures()
        reverse = discover_fixtures(sources=reversed(tuple(FIXTURE_BINDINGS)))
        self.assertEqual(canonical_json(forward), canonical_json(reverse))

    def test_observation_time_override_preserves_identity_and_payload(self):
        before = discover_fixtures()
        after = discover_fixtures(captured_at="2026-10-28T00:00:00Z")
        self.assertEqual(before["snapshot_id"], after["snapshot_id"])
        self.assertEqual(canonical_json(before["records"]), canonical_json(after["records"]))
        self.assertEqual(after["captured_at"], "2026-10-28T00:00:00Z")

    def test_invalid_unknown_or_repeated_source_selection_is_rejected(self):
        for sources in ([], ["unknown"], ["moark", "moark"]):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                discover_fixtures(sources=sources)

    def test_missing_source_is_an_error_not_a_smaller_silent_scope(self):
        path, data = self.temporary_manifest()
        del data["sources"]["moark"]
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            discover_fixtures(path)
        snapshot = discover_fixtures(path, sources=["huggingface"])
        self.assertEqual(snapshot, self.reference["sources"]["huggingface"]["snapshot"])

    def test_manifest_must_be_explicitly_synthetic_and_have_no_unknown_sources(self):
        for alter in (
            lambda data: data.update(synthetic=False),
            lambda data: data.update(format="another-format"),
            lambda data: data.update(captured_at=None),
            lambda data: data["sources"].update(unknown={}),
        ):
            with self.subTest(alter=alter):
                path, data = self.temporary_manifest()
                alter(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    discover_fixtures(path)

    def test_scope_mode_id_revision_and_provenance_errors_fail_closed(self):
        cases = [
            ("huggingface", lambda entry: entry["scope"].update(mode="crawl_all")),
            ("huggingface", lambda entry: entry["scope"].update(ids=["similar-but-different"])),
            ("huggingface", lambda entry: entry["scope"].update(ids=["one", "two"])),
            ("huggingface", lambda entry: entry.update(revision="fabricated")),
            ("models.dev", lambda entry: entry.update(revision="main")),
            ("models.dev", lambda entry: entry["scope"].update(limit=True)),
            ("csghub", lambda entry: entry["scope"].update(source="hf")),
            ("modelscope", lambda entry: entry["scope"].update(endpoint="https://other.test")),
            ("moark", lambda entry: entry["scope"].update(input="public_api")),
            ("moark", lambda entry: entry["scope"].update(authentication="authenticated")),
        ]
        for source, alter in cases:
            with self.subTest(source=source, alter=alter):
                path, data = self.temporary_manifest()
                alter(data["sources"][source])
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    discover_fixtures(path)

    def test_fixture_path_cannot_escape_or_use_a_symlink(self):
        for fixture in ("../outside.json", "/tmp/outside.json"):
            with self.subTest(fixture=fixture):
                path, data = self.temporary_manifest()
                data["sources"]["moark"]["fixture"] = fixture
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    discover_fixtures(path, sources=["moark"])
        path, data = self.temporary_manifest()
        (path.parent / "linked.json").symlink_to(path.parent / "moark_models.synthetic.json")
        data["sources"]["moark"]["fixture"] = "linked.json"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            discover_fixtures(path, sources=["moark"])
        path, _data = self.temporary_manifest()
        models = path.parent / "contracts_b40/models"
        models.rename(path.parent / "original-models")
        models.symlink_to(path.parent / "original-models", target_is_directory=True)
        with self.assertRaises(ValueError):
            discover_fixtures(path, sources=["models.dev"])

    def test_binding_rejects_wrong_namespace_type_or_revision_guarantee(self):
        snapshot = discover_fixtures(sources=["moark"])
        from source_adapters import SourceRecord
        entry = snapshot["records"][0]
        record = SourceRecord(**{key: value for key, value in entry.items() if key not in {"record_key", "payload_sha256"}})
        selection = FixtureSelection("moark", FIXTURES / "moark_models.synthetic.json", snapshot["scope"]["moark"], None, None)
        for changed in (replace(record, source="huggingface"), replace(record, entity_type="model_artifact"),
                        replace(record, source_revision="fabricated")):
            with self.subTest(source=changed.source, entity_type=changed.entity_type):
                binding = replace(FIXTURE_BINDINGS["moark"], normalize_fixture=lambda _: [changed])
                with self.assertRaises(ValueError):
                    binding.collect(selection)
        with self.assertRaises(ValueError):
            FIXTURE_BINDINGS["huggingface"].collect(selection)

    def test_discovery_does_not_modify_fixtures_or_b33_references(self):
        paths = [path for path in FIXTURES.rglob("*") if path.is_file()]
        before = {path: path.read_bytes() for path in paths}
        discover_fixtures()
        for path, content in before.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.read_bytes(), content)

    def test_common_cli_produces_only_a_synthetic_snapshot_on_stdout(self):
        result = guarded_cli("discover_sources.py", "--fixtures")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), discover_fixtures())
        self.assertIn("SYNTHETIC", result.stderr)
        self.assertIn("do not import", result.stderr)

    def test_common_cli_runs_each_of_seven_sources_without_network_sdk_or_db(self):
        for source in FIXTURE_BINDINGS:
            with self.subTest(source=source):
                result = guarded_cli("discover_sources.py", "--fixtures", "--source", source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(canonical_json(json.loads(result.stdout)), canonical_json(self.reference["sources"][source]["snapshot"]))

    def test_list_and_help_do_not_import_adapters_or_read_fixture_manifest(self):
        result = guarded_cli("discover_sources.py", "--list-sources", "--manifest", "/absent/manifest.json", deny_adapters=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({entry["source"] for entry in json.loads(result.stdout)}, set(FIXTURE_BINDINGS))
        result = guarded_cli("discover_sources.py", "--help", deny_adapters=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--fixtures", result.stdout)

    def test_no_online_mode_and_no_implicit_default_collection(self):
        for args in ((), ("--online",), ("--fixtures", "--online"), ("--source", "moark")):
            with self.subTest(args=args):
                result = guarded_cli("discover_sources.py", *args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_late_source_failure_has_no_partial_stdout_or_sensitive_diagnostics(self):
        path, data = self.temporary_manifest()
        bad = path.parent / "moark_models.synthetic.json"
        bad.write_text('{"object":"list","data":[{"api_key":"SYNTHETIC-DO-NOT-USE"}]}')
        with patch("sys.argv", ["discover_sources.py", "--fixtures", "--manifest", str(path)]), \
                patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(main(), 1)
            self.assertEqual(out.getvalue(), "")
            self.assertNotIn("SYNTHETIC-DO-NOT-USE", err.getvalue())
            self.assertNotIn(str(path), err.getvalue())

    def test_historical_b3_fixture_clis_still_match_frozen_snapshots(self):
        for source, script, filename in (
            ("modelscope", "probe_modelscope.py", "modelscope_repoinfo.synthetic.json"),
            ("csghub", "probe_csghub.py", "csghub_model_info.synthetic.json"),
            ("moark", "probe_moark.py", "moark_models.synthetic.json"),
        ):
            with self.subTest(source=source):
                result = guarded_cli(script, "--fixture", str(FIXTURES / filename))
                self.assertEqual(result.returncode, 0, result.stderr)
                actual = json.loads(result.stdout)
                expected = deepcopy(self.reference["sources"][source]["snapshot"])
                actual.pop("captured_at")
                expected.pop("captured_at")
                self.assertEqual(canonical_json(actual), canonical_json(expected))
        for script in ("collect_discovery_snapshot.py", "probe_source_adapters.py"):
            with self.subTest(script=script):
                result = guarded_cli(script, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
