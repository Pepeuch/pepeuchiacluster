"""Opt-in conditional metadata flow over an EXPLICIT trusted injected transport.

No default network client, collector, key store or DB. HTTP cache bindings are
separate from unchanged B2/B4 formats. A local attestation does not prove that a
provider answered or told the truth. Only anonymous fixed representations here.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import hashlib
import hmac
import math
import re
from urllib.parse import urlsplit
from urllib.request import Request

from discovery_cache import canonical_json, digest
from discovery_checkpoints import load_checkpoint, save_checkpoint
from discovery_execution import execute_source
from discovery_import_contract import validate_transition
from discovery_issuers import IssuerRegistry
from discovery_provenance import make_provenance, validation_context
from execution_models import Reason, SourceObservation, Status, validate_observation
from metadata_http import HTTPPolicy, MetadataHTTPError, MetadataResponseError, _validate_url
from metadata_primitives import copy_metadata, strict_json_loads
from source_spec_design import SOURCE_SPECS
from validated_discovery_cache import cache_request, http_validators, make_cache, reuse_not_modified, validate_cache


BINDING_FORMAT = "pepeuch-ai.http-representation-binding/v1"


@dataclass(frozen=True)
class ConditionalResponse:
    status: int
    body: bytes
    validators: dict
    target_url: str
    vary: tuple = ()
    no_store: bool = False


@dataclass(frozen=True)
class ConditionalRun:
    execution: object
    entry: dict | None
    binding: dict | None
    receipt: dict | None


def _instant(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Explicit bounded local observation time required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Local observation time requires timezone")
    return result


def _mac(value, key):
    return hmac.new(key, canonical_json(value).encode(), hashlib.sha256).hexdigest()


def _binding(entry, url, *, registry, issuer, key):
    registry.authorize(issuer, entry["request"]["source"], entry["request"]["context"], key=key)
    value = {"format": BINDING_FORMAT, "issuer": issuer, "target_url": url, "cache_sha256": digest(entry)}
    return {**value, "attestation": _mac(value, key)}


def validate_binding(entry, binding, *, url, registry):
    if not isinstance(registry, IssuerRegistry):
        raise ValueError("Explicit scoped issuer registry required")
    with registry.publication_guard():
        entry = validate_cache(entry, trusted_issuers=registry)
        value = copy_metadata(binding)
        if (entry["provenance"]["kind"] != "controlled_observation" or not isinstance(value, dict)
                or set(value) != {"format", "issuer", "target_url", "cache_sha256", "attestation"}
                or value["format"] != BINDING_FORMAT or value["target_url"] != url
                or value["cache_sha256"] != digest(entry)):
            raise ValueError("Exact authenticated HTTP representation binding required")
        key = registry.authorize(value["issuer"], entry["request"]["source"], entry["request"]["context"])
        expected = _binding(entry, url, registry=registry, issuer=value["issuer"], key=key)
        if (not isinstance(value["attestation"], str) or re.fullmatch(r"[0-9a-f]{64}", value["attestation"]) is None
                or not hmac.compare_digest(value["attestation"], expected["attestation"])):
            raise ValueError("HTTP representation binding attestation refused")
        return entry, value


def run_conditional(task, *, runtime, url, policy, transport, normalize, registry, issuer, key,
                    context, now, max_age_seconds, cache=None, binding=None, expected_revisions=None):
    """One representation GET per attempt, counted by the B4 budget engine.

    normalize(data, captured_at=now) returns a B2 snapshot. This explicit
    collaborator and the injected transport are trusted, not remote evidence.
    Expired baselines force an unconditional 200, never a silent stale fallback.
    """
    if not isinstance(registry, IssuerRegistry) or not isinstance(policy, HTTPPolicy):
        raise ValueError("Explicit scoped authority and HTTP policy required")
    if not callable(normalize) or not callable(getattr(transport, "fetch", None)):
        raise ValueError("Explicit transport and normalizer required; no network default")
    task = replace(task)
    if expected_revisions is not None:
        expected_revisions = copy_metadata(expected_revisions)
        cache_request(task.source, task.selection, [r.source_id for r in task.resources],
                      context=context, revisions=expected_revisions)
    context = validation_context(context)
    _validate_url(url, policy)
    host = urlsplit(url).hostname
    spec = SOURCE_SPECS[task.source]
    if (context["domain"] != host or context["account_partition"] != "anonymous"
            or host not in spec.transport.configured_hosts or spec.transport.kind == "official_sdk"):
        raise ValueError("Anonymous registered HTTP source and exact origin context required")
    registry.authorize(issuer, task.source, context, key=key)
    instant = _instant(now)
    if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(max_age_seconds) or not 0 <= max_age_seconds <= 604800):
        raise ValueError("Explicit local maximum age from zero to seven days required")
    if (cache is None) != (binding is None):
        raise ValueError("Cache and authenticated HTTP binding must be supplied together")
    previous, prior_binding = None, None
    if cache is not None:
        previous, prior_binding = validate_binding(cache, binding, url=url, registry=registry)
        request = cache_request(task.source, task.selection, [r.source_id for r in task.resources], context=context,
                                revisions=previous["request"]["revisions"] if expected_revisions is None else expected_revisions)
        if canonical_json(request) != canonical_json(previous["request"]):
            raise ValueError("Conditional request differs from the bound representation")
        age = (instant - _instant(previous["snapshot"]["captured_at"])).total_seconds()
        if age < 0:
            raise ValueError("Future cache observation refused")
    else:
        age = None
    accepted = {}

    def operation(attempt):
        accepted.clear()
        registry.authorize(issuer, task.source, context, key=key)
        sent = {"etag": None, "last_modified": None}
        def dispatch(remaining):
            elapsed = task.policy.total_seconds - remaining
            if previous is not None and age + elapsed < max_age_seconds:
                sent.update(copy_metadata(previous["validators"]))
            headers = {"Accept": "application/json", "User-Agent": "Pepeuch-AI-Discovery-POC/0.1"}
            if sent["etag"] is not None:
                headers["If-None-Match"] = sent["etag"]
            if sent["last_modified"] is not None:
                headers["If-Modified-Since"] = sent["last_modified"]
            return transport.fetch(Request(url, headers=headers, method="GET"),
                                   timeout=min(policy.timeout_seconds, remaining), max_bytes=policy.max_response_bytes)
        response = attempt.request(task.resources[0], dispatch)
        if not isinstance(response, ConditionalResponse) or type(response.status) is not int:
            raise MetadataResponseError("Invalid conditional HTTP result")
        if response.status not in (200, 304):
            raise MetadataHTTPError(response.status)
        if (response.target_url != url or type(response.vary) is not tuple or response.vary
                or type(response.no_store) is not bool or response.no_store
                or not isinstance(response.body, bytes) or len(response.body) > policy.max_response_bytes):
            raise ValueError("Unbound or unsupported HTTP representation")
        validators = http_validators(response.validators)
        with registry.publication_guard():
            registry.authorize(issuer, task.source, context, key=key)
            if previous is not None:
                validate_binding(previous, prior_binding, url=url, registry=registry)
            if response.status == 304:
                if response.body or previous is None or all(v is None for v in sent.values()):
                    raise ValueError("304 requires a known conditional representation without body")
                # Conservative profile: validator changes require a new 200.
                if validators != sent:
                    raise ValueError("304 validators contradict the conditional request")
                reused = reuse_not_modified(previous, previous["request"], sent_validators=sent, trusted_issuers=registry)
                snapshot = reused["snapshot"]
                entry, bound = previous, prior_binding
            else:
                payload = copy_metadata(strict_json_loads(response.body))
                if not isinstance(payload, dict):
                    raise ValueError("Metadata response must be an object")
                snapshot = validate_observation(task.source, task.selection, task.resources, normalize(payload, captured_at=now))
                if snapshot["captured_at"] != now:
                    raise ValueError("200 must carry this explicitly dated observation")
                if previous is not None:
                    validate_transition(previous["snapshot"], snapshot)
                    old = previous["validators"]
                    if snapshot["snapshot_id"] != previous["snapshot"]["snapshot_id"] and (
                        validators["etag"] is not None and validators["etag"] == old["etag"]
                        or validators["etag"] is None and old["etag"] is None and validators["last_modified"] is not None
                        and validators["last_modified"] == old["last_modified"]
                    ):
                        raise ValueError("Changed representation contradicts its unchanged validator")
                request = cache_request(task.source, task.selection, [r.source_id for r in task.resources], context=context,
                                        revisions={r["source_id"]: r["source_revision"] for r in snapshot["records"]})
                if expected_revisions is not None and request["revisions"] != expected_revisions:
                    raise ValueError("Observed revision differs from the explicit expectation")
                provenance = make_provenance(snapshot, kind="controlled_observation", context=context, issuer=issuer, key=key)
                entry = make_cache(request, snapshot, provenance, validators=validators, trusted_issuers=registry)
                bound = _binding(entry, url, registry=registry, issuer=issuer, key=key)
            accepted.update(entry=entry, binding=bound, status=response.status, validators=validators, sent=sent)
            return SourceObservation(snapshot, True)

    # The injected operation is explicit; old SourceTask/SourceObservation and
    # execution formats remain unchanged. No raw HTTPError(304) is promoted.
    result = execute_source(replace(task, operation=operation, synthetic=False), runtime=runtime)
    if result.status != Status.SUCCESS:
        return ConditionalRun(result, None, None, None)
    with registry.publication_guard():
        registry.authorize(issuer, task.source, context, key=key)
        entry, bound = validate_binding(accepted["entry"], accepted["binding"], url=url, registry=registry)
        if accepted["status"] == 304:
            final_age = (instant + timedelta(seconds=result.elapsed_seconds) - _instant(entry["snapshot"]["captured_at"])).total_seconds()
            if final_age >= max_age_seconds:
                failed = replace(result, status=Status.FAILED, reason=Reason.CACHE_REQUIRED, complete=False, snapshot=None)
                return ConditionalRun(failed, None, None, None)
            result = replace(result, status=Status.UNCHANGED)
        receipt = {"status": accepted["status"], "checked_at": (instant+timedelta(seconds=result.elapsed_seconds)).isoformat(),
                   "sent_validators": accepted["sent"],
                   "response_validators": accepted["validators"], "new_observation": accepted["status"] == 200,
                   "binding_sha256": digest(bound), "provider_truth_verified": False}
        return ConditionalRun(result, copy_metadata(entry), copy_metadata(bound), copy_metadata(receipt))


def archive_conditional(run, root, *, registry):
    if run.entry is None or run.binding is None or run.execution.status not in (Status.SUCCESS, Status.UNCHANGED):
        raise ValueError("Only successful bound observations may be archived")
    with registry.publication_guard():
        entry, binding = validate_binding(run.entry, run.binding, url=run.binding["target_url"], registry=registry)
        identity = save_checkpoint(root, entry, trusted_issuers=registry)
        return {"request": entry["request"], "identity": identity, "http_binding": binding}


def restore_conditional(root, descriptor, *, url, registry):
    descriptor = copy_metadata(descriptor)
    if not isinstance(descriptor, dict) or set(descriptor) != {"request", "identity", "http_binding"}:
        raise ValueError("Exact conditional resume descriptor required")
    with registry.publication_guard():
        entry = load_checkpoint(root, descriptor["request"], descriptor["identity"], trusted_issuers=registry)
        return validate_binding(entry, descriptor["http_binding"], url=url, registry=registry)
