"""Explicit fixture protection, with old snapshots/import interfaces preserved."""

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from discovery_cache import validate_snapshot
from discovery_registry import discover_fixtures
from discover_sources import main as discover_main
from emit_discovery_import import emit_pg, emit_surreal, main as emit_main
from synthetic_output import protect_fixture_snapshot
from test_discovery_registry import guarded_cli


class SyntheticOutputTests(unittest.TestCase):
    def setUp(self):
        for target in ("time.sleep", "socket.create_connection", "socket.socket.connect", "socket.getaddrinfo"):
            guard = patch(target, side_effect=AssertionError("Network/wait forbidden"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_envelope_preserves_all_b2_values_and_owns_its_inner_snapshot(self):
        snapshot = discover_fixtures()
        expected = deepcopy(snapshot)
        wrapped = protect_fixture_snapshot(snapshot)
        self.assertEqual(wrapped["format"], "pepeuch-ai.synthetic-discovery/v1")
        self.assertIs(wrapped["synthetic"], True)
        self.assertIs(wrapped["importable_as_real_observation"], False)
        self.assertEqual(wrapped["snapshot"], expected)
        validate_snapshot(wrapped["snapshot"])
        snapshot["records"][0]["display_name"] = "later mutation"
        self.assertEqual(wrapped["snapshot"], expected)

    def test_unchanged_import_generators_reject_envelope_before_any_statement(self):
        wrapped = protect_fixture_snapshot(discover_fixtures())
        for emitter in (emit_pg, emit_surreal):
            with self.subTest(emitter=emitter.__name__):
                output = io.StringIO()
                with self.assertRaises(ValueError):
                    emitter(wrapped, output)
                self.assertEqual(output.getvalue(), "")

    def test_import_cli_rejects_protected_file_without_sql_or_db_access(self):
        wrapped = protect_fixture_snapshot(discover_fixtures())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "SYNTHETIC-DO-NOT-IMPORT.json"
            path.write_text(json.dumps(wrapped))
            for engine in ("pg", "surreal"):
                with self.subTest(engine=engine), \
                        patch("sys.argv", ["emit_discovery_import.py", "--engine", engine, "--snapshot", str(path)]), \
                        patch("sys.stdout", new_callable=io.StringIO) as out, \
                        patch("sys.stderr", new_callable=io.StringIO):
                    self.assertEqual(emit_main(), 1)
                    self.assertEqual(out.getvalue(), "")

    def test_fixture_cli_default_is_unchanged_and_protection_is_explicit(self):
        outputs = []
        for flags in ([], ["--protected-output"]):
            with patch("sys.argv", ["discover_sources.py", "--fixtures", *flags]), \
                    patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(discover_main(), 0)
                outputs.append(json.loads(out.getvalue()))
        self.assertEqual(outputs[0], discover_fixtures())
        self.assertEqual(outputs[1]["snapshot"], outputs[0])

    def test_protected_cli_remains_offline_and_list_mode_stays_inert(self):
        result = guarded_cli("discover_sources.py", "--fixtures", "--protected-output")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["snapshot"], discover_fixtures())
        result = guarded_cli("discover_sources.py", "--list-sources", "--protected-output", deny_adapters=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_invalid_snapshot_cannot_be_made_to_look_protected_and_valid(self):
        with self.assertRaises(ValueError):
            protect_fixture_snapshot({"format": "pepeuch-ai.discovery-cache/v1", "records": []})


if __name__ == "__main__":
    unittest.main()
