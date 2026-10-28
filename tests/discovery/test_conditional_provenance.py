"""Scoped local authority and conditional HTTP, SYNTHETIC transport only."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest.mock import patch

from conditional_discovery import (ConditionalResponse, archive_conditional, restore_conditional,
                                   run_conditional, validate_binding)
from discovery_cache import canonical_json, make_snapshot
from discovery_issuers import IssuerRegistry
from discovery_provenance import validate_provenance
from execution_models import Status
from manual_discovery_run import fixture_tasks, run_manual
from metadata_http import HTTPPolicy
from metadata_http import MetadataHTTPError
from source_adapters import SourceRecord
from tests.discovery import POC_ROOT
import test_execution_b44 as b44
from validated_discovery_cache import cache_request, http_validators, validate_cache


URL = "https://huggingface.co/api/models/google/gemma-3-1b-it"
CONTEXT = {"domain": "huggingface.co", "account_partition": "anonymous", "representation": "metadata-v1"}
NOW = "2026-10-27T12:00:00+00:00"
LATER = "2026-10-27T12:00:10+00:00"


class Transport:
    def __init__(self, responses, callback=None):
        self.responses = list(responses)
        self.calls = []
        self.callback = callback

    def fetch(self, request, *, timeout, max_bytes):
        self.calls.append({"url": request.full_url, "method": request.get_method(),
                           "headers": dict(request.header_items()), "timeout": timeout, "max_bytes": max_bytes})
        if self.callback:
            self.callback()
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, BaseException):
            raise response
        return response


class ConditionalProvenance(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen", "time.sleep"):
            guard = patch(target, side_effect=AssertionError("No real transport or infrastructure"))
            guard.start()
            self.addCleanup(guard.stop)
        self.cases = json.loads((POC_ROOT/"fixtures/http_conditionals.synthetic.json").read_text())
        self.task, _, observation = b44.ExecutionB44Tests().task("huggingface")
        self.template = observation.snapshot
        self.clock = b44.FakeClock()
        self.registry = IssuerRegistry()
        self.key = secrets.token_bytes(32)
        self.registry.enroll("simulated-v1", self.key, grants=[{"source": "huggingface", "context": CONTEXT}])
        self.policy = HTTPPolicy({"huggingface.co"}, 100000, 20)
        temp = tempfile.TemporaryDirectory(prefix="conditional-synthetic-")
        self.addCleanup(temp.cleanup)
        self.archive = Path(temp.name)

    def response(self, name):
        case = self.cases["cases"][name]
        return ConditionalResponse(case["status"], b"" if case["payload"] is None else canonical_json(case["payload"]).encode(),
                                   deepcopy(case["validators"]), URL)

    def normalize(self, payload, *, captured_at):
        item = self.template["records"][0]
        record = SourceRecord(**{k: deepcopy(v) for k, v in item.items() if k not in {"record_key", "payload_sha256"}})
        record = replace(record, source_revision=payload.get("revision"), attributes={**record.attributes, "synthetic_http": payload.get("value")})
        return make_snapshot([record], scope=self.template["scope"], captured_at=captured_at)

    def run_http(self, name, previous=None, **changes):
        params = dict(runtime=self.clock.runtime(), url=URL, policy=self.policy,
                      transport=Transport([self.response(name)]), normalize=self.normalize,
                      registry=self.registry, issuer="simulated-v1", key=self.key, context=CONTEXT,
                      now=NOW if previous is None else LATER, max_age_seconds=60,
                      cache=None if previous is None else previous.entry, binding=None if previous is None else previous.binding)
        params.update(changes)
        transport = params["transport"]
        result = run_conditional(self.task, **params)
        return result, transport

    def initial(self):
        result, _ = self.run_http("initial_200")
        self.assertEqual(result.execution.status, Status.SUCCESS)
        return result

    def test_malformed_etags_and_last_modified_are_rejected(self):
        for field, values in (("etag", self.cases["invalid_etags"]), ("last_modified", self.cases["invalid_last_modified"])):
            for value in values:
                validators = {"etag": None, "last_modified": None, field: value}
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    http_validators(validators)

    def test_valid_empty_and_weak_etags_are_opaque(self):
        for tag in ('""', 'W/"v1"', '"back\\slash"'):
            self.assertEqual(http_validators({"etag": tag, "last_modified": None})["etag"], tag)

    def test_200_new_representation_has_scoped_provenance_and_counts_one_request(self):
        first = self.initial()
        second, transport = self.run_http("new_200", first)
        self.assertEqual(second.execution.status, Status.SUCCESS)
        self.assertEqual(second.execution.requests, 1)
        self.assertNotEqual(second.entry["snapshot"]["snapshot_id"], first.entry["snapshot"]["snapshot_id"])
        self.assertEqual(second.entry["snapshot"]["captured_at"], LATER)
        self.assertEqual(second.entry["request"]["revisions"], {self.task.resources[0].source_id: "synthetic-http-r2"})
        self.assertTrue(second.receipt["new_observation"])
        self.assertFalse(second.receipt["provider_truth_verified"])
        self.assertEqual(transport.calls[0]["headers"]["If-none-match"], '"synthetic-v1"')
        validate_provenance(second.entry["snapshot"], second.entry["provenance"], trusted_issuers=self.registry)

    def test_304_keeps_exact_capture_provenance_binding_and_checkpoint(self):
        first = self.initial()
        descriptor = archive_conditional(first, self.archive, registry=self.registry)
        original = canonical_json(first.entry)
        second, _ = self.run_http("valid_304", first)
        self.assertEqual(second.execution.status, Status.UNCHANGED)
        self.assertEqual(canonical_json(second.entry), original)
        self.assertEqual(second.binding, first.binding)
        self.assertFalse(second.receipt["new_observation"])
        self.assertEqual(archive_conditional(second, self.archive, registry=self.registry), descriptor)
        self.assertEqual(len(list(self.archive.glob("*.json"))), 1)

    def test_304_without_previous_representation_fails_without_retry(self):
        result, transport = self.run_http("valid_304")
        self.assertEqual(result.execution.status, Status.FAILED)
        self.assertEqual(len(transport.calls), 1)
        self.assertIsNone(result.entry)

    def test_304_with_incoherent_etag_or_body_is_refused(self):
        first = self.initial()
        for name in ("wrong_etag_304", "body_on_304"):
            result, _ = self.run_http(name, first)
            self.assertEqual(result.execution.status, Status.FAILED)
            self.assertIsNone(result.entry)

    def test_validatorless_representation_cannot_establish_a_conditional_304(self):
        first, _ = self.run_http("validatorless_200")
        second, transport = self.run_http("validatorless_304", first)
        self.assertEqual(second.execution.status, Status.FAILED)
        self.assertNotIn("If-none-match", transport.calls[0]["headers"])

    def test_last_modified_only_304_keeps_explicit_unknown_revision(self):
        first, _ = self.run_http("last_modified_200")
        second, transport = self.run_http("last_modified_304", first)
        self.assertEqual(second.execution.status, Status.UNCHANGED)
        self.assertIn("If-modified-since", transport.calls[0]["headers"])
        self.assertIsNone(second.entry["request"]["revisions"][self.task.resources[0].source_id])

    def test_expiry_forces_unconditional_200_and_never_renews_capture_via_304(self):
        first = self.initial()
        second, transport = self.run_http("valid_304", first, max_age_seconds=5)
        self.assertEqual(second.execution.status, Status.FAILED)
        self.assertNotIn("If-none-match", transport.calls[0]["headers"])
        third, transport = self.run_http("new_200", first, max_age_seconds=5)
        self.assertEqual(third.execution.status, Status.SUCCESS)
        self.assertNotIn("If-none-match", transport.calls[0]["headers"])
        self.assertEqual(first.entry["snapshot"]["captured_at"], NOW)

    def test_expiry_during_request_prevents_publication(self):
        first = self.initial()
        transport = Transport([self.response("valid_304")], callback=lambda: setattr(self.clock, "now", self.clock.now+2))
        result, _ = self.run_http("valid_304", first, transport=transport, now="2026-10-27T12:00:09+00:00", max_age_seconds=10)
        self.assertEqual(result.execution.status, Status.FAILED)
        self.assertEqual(result.execution.reason.value, "validated_cache_required")
        self.assertIsNone(result.entry)

    def test_expiry_during_retry_wait_removes_condition_for_next_request(self):
        first = self.initial()
        transport = Transport([MetadataHTTPError(503), self.response("new_200")])
        result, _ = self.run_http("new_200", first, transport=transport,
                                  now="2026-10-27T12:00:00.400000+00:00", max_age_seconds=.5)
        self.assertEqual(result.execution.status, Status.SUCCESS)
        self.assertEqual(result.execution.requests, 2)
        self.assertIn("If-none-match", transport.calls[0]["headers"])
        self.assertNotIn("If-none-match", transport.calls[1]["headers"])

    def test_domain_partition_or_representation_change_fails_before_transport(self):
        first = self.initial()
        for field, value in (("domain", "other.invalid"), ("account_partition", "private"), ("representation", "other-v2")):
            transport = Transport([self.response("valid_304")])
            with self.assertRaises(ValueError):
                self.run_http("valid_304", first, transport=transport, context={**CONTEXT, field: value})
            self.assertEqual(transport.calls, [])

    def test_path_change_cannot_reuse_a_binding_even_on_same_domain(self):
        first = self.initial()
        with self.assertRaises(ValueError):
            self.run_http("valid_304", first, url=URL+"/different")

    def test_unknown_or_revoked_issuer_cannot_dispatch_or_publish(self):
        for issuer in ("unknown", "simulated-v1"):
            if issuer == "simulated-v1":
                self.registry.revoke(issuer)
            transport = Transport([self.response("initial_200")])
            with self.assertRaises(ValueError):
                self.run_http("initial_200", issuer=issuer, transport=transport)
            self.assertEqual(transport.calls, [])

    def test_source_grant_is_not_global_and_alias_never_resurrects(self):
        with self.assertRaises(ValueError):
            self.registry.authorize("simulated-v1", "csghub", CONTEXT)
        self.registry.revoke("simulated-v1")
        with self.assertRaises(ValueError):
            self.registry.enroll("simulated-v1", self.key, grants=[{"source": "huggingface", "context": CONTEXT}])
        self.assertNotIn(self.key.hex(), repr(self.registry))

    def test_rotation_uses_new_alias_and_refuses_old_archive(self):
        first = self.initial()
        descriptor = archive_conditional(first, self.archive, registry=self.registry)
        new_key = secrets.token_bytes(32)
        self.registry.rotate("simulated-v1", "simulated-v2", new_key)
        with self.assertRaises(ValueError):
            restore_conditional(self.archive, descriptor, url=URL, registry=self.registry)
        second, _ = self.run_http("new_200", issuer="simulated-v2", key=new_key)
        self.assertEqual(second.execution.status, Status.SUCCESS)

    def test_rotation_or_enrollment_cannot_resurrect_a_key_under_new_alias(self):
        with self.assertRaises(ValueError):
            self.registry.rotate("simulated-v1", "simulated-v2", self.key)
        self.registry.authorize("simulated-v1", "huggingface", CONTEXT)
        self.registry.revoke("simulated-v1")
        with self.assertRaises(ValueError):
            self.registry.enroll("resurrected", self.key, grants=[{"source": "huggingface", "context": CONTEXT}])

    def test_revocation_during_transport_refuses_result(self):
        transport = Transport([self.response("initial_200")], callback=lambda: self.registry.revoke("simulated-v1"))
        result, _ = self.run_http("initial_200", transport=transport)
        self.assertEqual(result.execution.status, Status.FAILED)
        self.assertIsNone(result.entry)

    def test_revocation_before_archive_never_writes(self):
        first = self.initial()
        self.registry.revoke("simulated-v1")
        with self.assertRaises(ValueError):
            archive_conditional(first, self.archive, registry=self.registry)
        self.assertEqual(list(self.archive.iterdir()), [])

    def test_publication_finishes_before_concurrent_revocation_then_resume_is_refused(self):
        first = self.initial()
        entered, release, attempted, revoked = (threading.Event() for _ in range(4))
        saved, errors = [], []
        import discovery_checkpoints
        original_replace = discovery_checkpoints.os.replace
        def pause(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Synthetic publication gate timed out")
            return original_replace(*args, **kwargs)
        def publish():
            try:
                saved.append(archive_conditional(first, self.archive, registry=self.registry))
            except BaseException as exc:
                errors.append(type(exc).__name__)
        def revoke():
            attempted.set()
            self.registry.revoke("simulated-v1")
            revoked.set()
        publisher, revoker = threading.Thread(target=publish), threading.Thread(target=revoke)
        with patch("discovery_checkpoints.os.replace", side_effect=pause):
            publisher.start()
            try:
                self.assertTrue(entered.wait(2))
                revoker.start()
                self.assertTrue(attempted.wait(2))
                self.assertFalse(revoked.is_set())
            finally:
                release.set()
                publisher.join(3)
                if revoker.ident is not None:
                    revoker.join(3)
        self.assertFalse(publisher.is_alive() or revoker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(saved), 1)
        self.assertTrue(revoked.is_set())
        self.assertEqual(len(list(self.archive.glob("*.json"))), 1)
        with self.assertRaises(ValueError):
            restore_conditional(self.archive, saved[0], url=URL, registry=self.registry)

    def test_signed_snapshot_does_not_authenticate_tampered_http_validators(self):
        first = self.initial()
        cache = deepcopy(first.entry)
        cache["validators"]["etag"] = '"forged-association"'
        validate_cache(cache, trusted_issuers=self.registry)  # Legacy B4 structure only.
        with self.assertRaises(ValueError):
            validate_binding(cache, first.binding, url=URL, registry=self.registry)

    def test_explicit_revision_change_or_malformed_expectation_refuses_reuse(self):
        first = self.initial()
        for revisions in ({}, {self.task.resources[0].source_id: "other-revision"}, {self.task.resources[0].source_id: "\r\ninvalid"}):
            with self.assertRaises(ValueError):
                self.run_http("valid_304", first, expected_revisions=revisions)

    def test_malformed_observed_revision_never_publishes(self):
        result, _ = self.run_http("malformed_revision_200")
        self.assertEqual(result.execution.status, Status.FAILED)
        self.assertIsNone(result.entry)

    def test_same_instant_conflicting_observation_is_refused(self):
        first = self.initial()
        result, _ = self.run_http("new_200", first, now=NOW)
        self.assertEqual(result.execution.status, Status.FAILED)

    def test_new_payload_with_unchanged_etag_is_refused(self):
        first = self.initial()
        response = replace(self.response("new_200"), validators=first.entry["validators"])
        result, _ = self.run_http("new_200", first, transport=Transport([response]))
        self.assertEqual(result.execution.status, Status.FAILED)

    def test_transport_errors_never_fall_back_to_old_data_or_leak_text(self):
        first = self.initial()
        result, transport = self.run_http("valid_304", first, transport=Transport([TimeoutError("synthetic-error-marker")]))
        self.assertNotIn(result.execution.status, (Status.SUCCESS, Status.UNCHANGED))
        self.assertIsNone(result.entry)
        self.assertNotIn("synthetic-error-marker", canonical_json(result.execution.to_manifest()))
        self.assertLessEqual(len(transport.calls), self.task.policy.max_requests)

    def test_unsupported_variance_no_store_redirect_or_oversize_is_refused(self):
        response = self.response("initial_200")
        for value in (replace(response, vary=("Accept-Language",)), replace(response, no_store=True),
                      replace(response, target_url=URL+"/redirect"), replace(response, body=b"x"*100001)):
            result, _ = self.run_http("initial_200", transport=Transport([value]))
            self.assertEqual(result.execution.status, Status.FAILED)

    def test_resume_after_interrupted_checkpoint_preserves_explicit_old_generation(self):
        first = self.initial()
        original = archive_conditional(first, self.archive, registry=self.registry)
        second, _ = self.run_http("new_200", first)
        with patch("discovery_checkpoints.os.replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                archive_conditional(second, self.archive, registry=self.registry)
        entry, binding = restore_conditional(self.archive, original, url=URL, registry=self.registry)
        self.assertEqual(entry, first.entry)
        self.assertEqual(binding, first.binding)
        updated = archive_conditional(second, self.archive, registry=self.registry)
        self.assertNotEqual(updated["identity"], original["identity"])
        self.assertEqual(len(list(self.archive.glob("*.json"))), 2)

    def test_manual_resume_rechecks_revocation_between_sources(self):
        tasks = [replace(t, synthetic=False) for t in fixture_tasks(["huggingface", "csghub"])]
        contexts = {t.source: {**CONTEXT, "domain": "fixtures.invalid"} for t in tasks}
        authority = IssuerRegistry()
        authority.enroll("manual-v1", self.key, grants=[{"source": t.source, "context": contexts[t.source]} for t in tasks])
        params = dict(runtime=self.clock.runtime(), archive=self.archive, contexts=contexts, now=NOW,
                      max_age_seconds=86400, trusted_issuers=authority, issuer="manual-v1", key=self.key)
        initial = run_manual(tasks, **params)
        resume = {e["source"]: e["resume"] for e in initial["sources"]}
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.archive.glob("*.json")}
        events = []
        def revoke(event):
            events.append(event)
            authority.revoke("manual-v1")
        with self.assertRaises(ValueError):
            run_manual(tasks, resume=resume, on_event=revoke, **params)
        self.assertEqual(len(events), 1)
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.archive.glob("*.json")}, hashes)
