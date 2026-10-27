"""B4.5 resilience with synthetic fixtures and private temporary POSIX storage.

Attestations below simulate a locally enrolled issuer; NO real observation is
made or claimed. Ephemeral test keys are generated at runtime, never committed.
"""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from discovery_cache import canonical_json, digest
from discovery_checkpoints import load_checkpoint, save_checkpoint, _directory, _writer
from discovery_execution import execute_sources
from discovery_provenance import make_provenance, validate_provenance, emit_protected
from discovery_registry import discover_fixtures
from emit_discovery_import import emit_pg, emit_surreal
from execution_models import Status
from metadata_http import MetadataHTTPError
import test_execution_b44 as b44
from validated_discovery_cache import cache_request, make_cache, validate_cache, reuse_not_modified


ROOT = Path(__file__).resolve().parent
CONTEXT = {"domain": "huggingface.co", "account_partition": "anonymous", "representation": "metadata-v1"}
VALIDATORS = {"etag": '"fixture-version-1"', "last_modified": None}


class RecoveryB45Tests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen", "time.sleep"):
            guard = patch(target, side_effect=AssertionError("Offline B4.5 test"))
            guard.start()
            self.addCleanup(guard.stop)
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b45-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.snapshot = discover_fixtures(sources=["huggingface"])
        self.key = secrets.token_bytes(32)
        self.trusted = {"simulated-issuer": self.key}
        self.provenance = self.provenance_for(self.snapshot)
        self.request = self.request_for(self.snapshot)
        self.entry = make_cache(self.request, self.snapshot, self.provenance, validators=VALIDATORS)

    def provenance_for(self, snapshot, kind="synthetic", context=None):
        kwargs = {"issuer": "simulated-issuer", "key": self.key} if kind == "controlled_observation" else {}
        return make_provenance(snapshot, kind=kind, context=CONTEXT if context is None else context, **kwargs)

    def request_for(self, snapshot, context=None):
        source = next(iter(snapshot["scope"]))
        return cache_request(source, snapshot["scope"][source], [r["source_id"] for r in snapshot["records"]],
                             context=CONTEXT if context is None else context,
                             revisions={r["source_id"]: r["source_revision"] for r in snapshot["records"]})

    def reuse(self, entry=None, request=None, validators=None):
        return reuse_not_modified(self.entry if entry is None else entry, self.request if request is None else request,
                                 sent_validators=VALIDATORS if validators is None else validators, trusted_issuers=self.trusted)

    def test_three_provenance_kinds_explicitly_distinct(self):
        for kind in ("synthetic", "controlled_observation", "historical_unknown"):
            p = self.provenance_for(self.snapshot, kind)
            self.assertEqual(validate_provenance(self.snapshot, p, trusted_issuers=self.trusted)["kind"], kind)
            self.assertEqual(p["snapshot_id"], self.snapshot["snapshot_id"])
            self.assertEqual(p["snapshot_sha256"], digest(self.snapshot))

    def test_boolean_origin_declaration_is_not_provenance(self):
        with self.assertRaises(ValueError):
            validate_provenance(self.snapshot, {"synthetic": False})

    def test_untrusted_or_wrong_signing_key_refused(self):
        p = self.provenance_for(self.snapshot, "controlled_observation")
        for trust in ({}, {"simulated-issuer": secrets.token_bytes(32)}):
            with self.assertRaises(ValueError):
                validate_provenance(self.snapshot, p, trusted_issuers=trust)

    def test_tampered_attestation_and_context_refused(self):
        p = self.provenance_for(self.snapshot, "controlled_observation")
        for field, value in (("attestation", "0" * 64), ("context", {**CONTEXT, "account_partition": "other"})):
            changed = deepcopy(p)
            changed[field] = value
            with self.assertRaises(ValueError):
                validate_provenance(self.snapshot, changed, trusted_issuers=self.trusted)

    def test_timestamp_bound_even_though_b2_identity_excludes_it(self):
        changed = deepcopy(self.snapshot)
        changed["captured_at"] = "2026-10-28T00:00:00+00:00"
        self.assertEqual(changed["snapshot_id"], self.snapshot["snapshot_id"])
        with self.assertRaises(ValueError):
            validate_provenance(changed, self.provenance)

    def test_known_moark_synthetic_scope_cannot_be_promoted(self):
        with self.assertRaises(ValueError):
            self.provenance_for(discover_fixtures(sources=["moark"]), "controlled_observation")

    def test_protected_path_rejects_synthetic_and_unknown_without_output(self):
        for kind in ("synthetic", "historical_unknown"):
            for engine in ("pg", "surreal"):
                stream = io.StringIO()
                with self.assertRaises(ValueError):
                    emit_protected(self.snapshot, self.provenance_for(self.snapshot, kind),
                                   trusted_issuers=self.trusted, engine=engine, stream=stream)
                self.assertEqual(stream.getvalue(), "")

    def test_protected_output_exactly_matches_legacy_generators_for_simulated_trusted_issuer(self):
        p = self.provenance_for(self.snapshot, "controlled_observation")
        for engine, emitter in (("pg", emit_pg), ("surreal", emit_surreal)):
            expected, output = io.StringIO(), io.StringIO()
            emitter(self.snapshot, expected)
            emit_protected(self.snapshot, p, trusted_issuers=self.trusted, engine=engine, stream=output)
            self.assertEqual(output.getvalue(), expected.getvalue())
            self.assertNotIn("DELETE ", output.getvalue())

    def test_protected_untrusted_has_no_output(self):
        stream = io.StringIO()
        with self.assertRaises(ValueError):
            emit_protected(self.snapshot, self.provenance_for(self.snapshot, "controlled_observation"),
                           trusted_issuers={}, engine="pg", stream=stream)
        self.assertEqual(stream.getvalue(), "")

    def test_cache_absent(self):
        with self.assertRaises(ValueError):
            reuse_not_modified(None, self.request, sent_validators=VALIDATORS)

    def test_historical_unknown_cannot_establish_304_baseline(self):
        entry = make_cache(self.request, self.snapshot, self.provenance_for(self.snapshot, "historical_unknown"), validators=VALIDATORS)
        with self.assertRaises(ValueError):
            self.reuse(entry=entry)

    def test_corrupt_existing_generation_is_not_overwritten(self):
        identity = save_checkpoint(self.directory, self.entry)
        path = self.directory / (identity + ".json")
        path.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            save_checkpoint(self.directory, self.entry)
        self.assertEqual(path.read_bytes(), b"corrupt")

    def test_short_writes_are_completed(self):
        import os
        actual_write = os.write
        with patch("discovery_checkpoints.os.write", side_effect=lambda fd, data: actual_write(fd, data[:97])):
            identity = save_checkpoint(self.directory, self.entry)
        self.assertEqual(load_checkpoint(self.directory, self.request, identity), self.entry)

    def test_same_scope_cache_reuses_exact_observation(self):
        result = self.reuse()
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["snapshot"], self.snapshot)
        result["snapshot"]["records"][0]["attributes"]["modified"] = True
        self.assertEqual(self.entry["snapshot"], self.snapshot)

    def test_cache_different_selection_refused(self):
        changed = deepcopy(self.request)
        identity = "other/model"
        changed["selection"]["ids"] = [identity]
        changed["resources"] = [identity]
        changed["revisions"] = {identity: None}
        with self.assertRaises(ValueError):
            self.reuse(request=changed)

    def test_context_isolates_domains_accounts_and_representations(self):
        for field in CONTEXT:
            changed = deepcopy(self.request)
            changed["context"][field] = "another-public-partition"
            with self.assertRaises(ValueError):
                self.reuse(request=changed)

    def test_incompatible_revision_refused(self):
        changed = deepcopy(self.request)
        changed["revisions"][changed["resources"][0]] = "different-revision"
        with self.assertRaises(ValueError):
            self.reuse(request=changed)

    def test_conditional_validators_must_be_present_and_match(self):
        for sent in ({"etag": None, "last_modified": None}, {"etag": '"other"', "last_modified": None}):
            with self.assertRaises(ValueError):
                self.reuse(validators=sent)

    def test_nim_identity_remains_resource_not_tag_and_conditional_validation_required(self):
        snapshot = discover_fixtures(sources=["nvidia-nim-metadata"])
        request = self.request_for(snapshot)
        entry = make_cache(request, snapshot, self.provenance_for(snapshot), validators=VALIDATORS)
        self.assertEqual(reuse_not_modified(entry, request, sent_validators=VALIDATORS)["snapshot"], snapshot)
        changed = deepcopy(request)
        changed["selection"]["tag"] = "new-tag"
        changed["revisions"][changed["resources"][0]] = "new-tag"
        with self.assertRaises(ValueError):
            reuse_not_modified(entry, changed, sent_validators=VALIDATORS)
        self.assertEqual(snapshot["records"][0]["source_id"], request["selection"]["resource_id"])

    def test_incomplete_cache_cannot_publish(self):
        changed = deepcopy(self.entry)
        changed["validation"] = "partial"
        with self.assertRaises(ValueError):
            validate_cache(changed)

    def test_cache_payload_corruption_rejected(self):
        changed = deepcopy(self.entry)
        changed["snapshot"]["records"][0]["display_name"] = "corrupted"
        with self.assertRaises(ValueError):
            validate_cache(changed)

    def test_cache_snapshot_digest_corruption_rejected(self):
        changed = deepcopy(self.entry)
        changed["snapshot_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_cache(changed)

    def test_cache_metadata_is_defensively_copied(self):
        self.snapshot["records"][0]["attributes"]["changed_after_validation"] = True
        self.request["context"]["representation"] = "changed"
        self.assertNotIn("changed_after_validation", self.entry["snapshot"]["records"][0]["attributes"])
        self.assertEqual(self.entry["request"]["context"], CONTEXT)

    def test_restart_and_repeat_are_idempotent(self):
        identity = save_checkpoint(self.directory, self.entry)
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        # Load via a new call with only serialized request and explicit generation.
        recovered = load_checkpoint(str(self.directory), json.loads(json.dumps(self.request)), identity)
        self.assertEqual(recovered, self.entry)
        self.assertEqual(save_checkpoint(self.directory, recovered), identity)
        self.assertEqual({p.name: p.read_bytes() for p in self.directory.iterdir()}, before)

    def test_truncated_checkpoint_refused(self):
        identity = save_checkpoint(self.directory, self.entry)
        (self.directory / (identity + ".json")).write_text('{"format":')
        with self.assertRaises(ValueError):
            load_checkpoint(self.directory, self.request, identity)

    def test_checkpoint_integrity_corruption_refused(self):
        identity = save_checkpoint(self.directory, self.entry)
        path = self.directory / (identity + ".json")
        data = json.loads(path.read_text())
        data["entry"]["validators"]["etag"] = '"corrupted"'
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_checkpoint(self.directory, self.request, identity)

    def test_wrong_scope_or_generation_is_never_implicitly_restored(self):
        identity = save_checkpoint(self.directory, self.entry)
        changed = deepcopy(self.request)
        changed["context"]["account_partition"] = "other"
        for request, generation in ((changed, identity), (self.request, "../elsewhere"), (self.request, "latest")):
            with self.assertRaises(ValueError):
                load_checkpoint(self.directory, request, generation)

    def test_interruption_before_validation_does_not_write(self):
        with patch("discovery_checkpoints.validate_cache", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                save_checkpoint(self.directory, self.entry)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_interruption_while_writing_preserves_previous_generation(self):
        identity = save_checkpoint(self.directory, self.entry)
        changed = deepcopy(self.entry)
        changed["validators"]["etag"] = '"next-version"'
        with patch("discovery_checkpoints.os.write", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                save_checkpoint(self.directory, changed)
        self.assertEqual(load_checkpoint(self.directory, self.request, identity), self.entry)
        self.assertEqual(len(list(self.directory.glob("*.json"))), 1)
        self.assertEqual(list(self.directory.glob(".pending-*")), [])

    def test_interruption_before_publication_and_restart(self):
        with patch("discovery_checkpoints.os.replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                save_checkpoint(self.directory, self.entry)
        self.assertEqual(list(self.directory.glob("*.json")), [])
        identity = save_checkpoint(self.directory, self.entry)
        self.assertEqual(load_checkpoint(self.directory, self.request, identity), self.entry)

    def test_interruption_after_atomic_publication_is_recoverable(self):
        with patch("discovery_checkpoints.os.fsync", side_effect=[None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                save_checkpoint(self.directory, self.entry)
        # Simulated process interruption after publication, not a power-loss test.
        identity = save_checkpoint(self.directory, self.entry)
        self.assertEqual(load_checkpoint(self.directory, self.request, identity), self.entry)

    def test_old_generations_preserved_no_automatic_deletion(self):
        first = save_checkpoint(self.directory, self.entry)
        next_entry = deepcopy(self.entry)
        next_entry["validators"]["etag"] = '"next-version"'
        second = save_checkpoint(self.directory, next_entry)
        self.assertNotEqual(first, second)
        self.assertEqual(load_checkpoint(self.directory, self.request, first), self.entry)
        self.assertEqual(load_checkpoint(self.directory, self.request, second), next_entry)
        self.assertEqual(len(list(self.directory.glob("*.json"))), 2)

    def test_concurrent_writer_is_refused(self):
        with _directory(self.directory) as directory, _writer(directory):
            with self.assertRaisesRegex(ValueError, "Concurrent"):
                save_checkpoint(self.directory, self.entry)
        self.assertEqual(list(self.directory.glob("*.json")), [])

    def test_symlink_root_or_ancestor_refused(self):
        alias = self.directory / "alias"
        real = self.directory / "private"
        real.mkdir(mode=0o700)
        alias.symlink_to(real, target_is_directory=True)
        for root in (alias, alias / "child"):
            with self.assertRaises(OSError):
                save_checkpoint(root, self.entry)

    def test_symlink_final_checkpoint_and_lock_refused(self):
        identity = save_checkpoint(self.directory, self.entry)
        path = self.directory / (identity + ".json")
        target = self.directory / "safe-copy"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(OSError):
            load_checkpoint(self.directory, self.request, identity)
        lock = self.directory / ".writer.lock"
        lock.unlink()
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            save_checkpoint(self.directory, self.entry)

    def test_unsafe_directory_permissions_and_paths_refused(self):
        self.directory.chmod(0o755)
        with self.assertRaises(ValueError):
            save_checkpoint(self.directory, self.entry)
        self.directory.chmod(0o700)
        for path in ("relative", str(self.directory / ".." / self.directory.name)):
            with self.assertRaises(ValueError):
                save_checkpoint(path, self.entry)

    def test_oversized_checkpoint_refused(self):
        with patch("discovery_checkpoints.MAX_BYTES", 100):
            with self.assertRaises(ValueError):
                save_checkpoint(self.directory, self.entry)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_crash_residue_never_restored_or_deleted_implicitly(self):
        residue = self.directory / ".pending-interrupted-process"
        residue.write_text("incomplete")
        identity = save_checkpoint(self.directory, self.entry)
        self.assertEqual(load_checkpoint(self.directory, self.request, identity), self.entry)
        self.assertEqual(residue.read_text(), "incomplete")

    def test_sensitive_nested_metadata_refused_before_persistence(self):
        changed = deepcopy(self.entry)
        changed["snapshot"]["records"][0]["raw_metadata"]["nested"] = [{"Authorization": "redacted-synthetic-value"}]
        with self.assertRaises(ValueError):
            save_checkpoint(self.directory, changed)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_sensitive_context_and_header_values_refused(self):
        for context in ({**CONTEXT, "password": "redacted-synthetic-value"}, {**CONTEXT, "domain": "https://user@example.test"}):
            with self.assertRaises(ValueError):
                self.provenance_for(self.snapshot, context=context)
        with self.assertRaises(ValueError):
            self.reuse(validators={"etag": '"a"\r\nCookie: nope', "last_modified": None})

    def test_all_seven_fixture_snapshots_roundtrip_without_b2_changes(self):
        for source in discover_fixtures()["scope"]:
            with self.subTest(source=source):
                snapshot = discover_fixtures(sources=[source])
                request = self.request_for(snapshot)
                entry = make_cache(request, snapshot, self.provenance_for(snapshot), validators=VALIDATORS)
                identity = save_checkpoint(self.directory, entry)
                restored = load_checkpoint(self.directory, request, identity)
                self.assertEqual(canonical_json(restored["snapshot"]), canonical_json(snapshot))
                self.assertEqual(reuse_not_modified(restored, request, sent_validators=VALIDATORS)["snapshot"], snapshot)

    def test_b33_literal_reference_file_is_unchanged(self):
        raw = (ROOT / "fixtures/contracts_b40/reference.b33.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd")

    def test_b44_304_still_fails_and_other_sources_can_be_checkpointed(self):
        # Reuse the existing pure fixture plan builder without inheriting its tests.
        helper = b44.ExecutionB44Tests()
        good, _, _ = helper.task("huggingface")
        bad, _, _ = helper.task("moark", actions=[MetadataHTTPError(304)])
        report = execute_sources([good, bad], runtime=b44.FakeClock().runtime())
        self.assertEqual([r.status for r in report.results], [Status.SUCCESS, Status.FAILED])
        self.assertEqual(report.results[1].reason.value, "validated_cache_required")
        first = save_checkpoint(self.directory, self.entry)
        self.assertEqual(load_checkpoint(self.directory, self.request, first), self.entry)
        self.assertIsNone(report.results[1].snapshot)


if __name__ == "__main__":
    unittest.main()
