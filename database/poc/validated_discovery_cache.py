"""B4.5 explicit single-source cache and offline 304 validation contract.

No HTTP calls or implicit wiring into B4.4. The caller supplies evidence of the
conditional request; this module cannot prove that a request actually occurred.
"""

from __future__ import annotations

from email.utils import format_datetime, parsedate_to_datetime
import re

from discovery_cache import digest
from discovery_provenance import snapshot_copy, validate_provenance, validation_context
from execution_models import ResourceRef, safe_selection, validate_observation
from metadata_primitives import copy_metadata


FORMAT = "pepeuch-ai.validated-discovery-cache/v1"


def cache_request(source, selection, resources, *, context, revisions):
    selection = safe_selection(source, selection)
    refs = tuple(ResourceRef(source, identity) for identity in resources)
    if not refs or len(set(refs)) != len(refs):
        raise ValueError("Distinct requested resources required")
    ids = sorted(ref.source_id for ref in refs)
    if selection["mode"] == "exact_ids" and set(ids) != set(selection["ids"]):
        raise ValueError("Requested resources differ from selection")
    if selection["mode"] == "exact_tag" and ids != [selection["resource_id"]]:
        raise ValueError("Requested NIM resource differs from selection")
    revisions = copy_metadata(revisions)
    if not isinstance(revisions, dict) or set(revisions) != set(ids) or any(
        v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 256
                          or any(ord(c) < 32 or ord(c) == 127 for c in v)) for v in revisions.values()
    ):
        raise ValueError("Explicit current revision expectations required, including unknowns")
    return {"source": source, "selection": selection, "resources": ids,
            "context": validation_context(context), "revisions": revisions}


def _request(value):
    data = copy_metadata(value)
    if not isinstance(data, dict) or set(data) != {"source", "selection", "resources", "context", "revisions"}:
        raise ValueError("Exact cache request required")
    expected = cache_request(data["source"], data["selection"], data["resources"],
                             context=data["context"], revisions=data["revisions"])
    if data != expected:
        raise ValueError("Canonical cache request required")
    return expected


def http_validators(value):
    data = copy_metadata(value)
    if not isinstance(data, dict) or set(data) != {"etag", "last_modified"}:
        raise ValueError("Explicit HTTP validators required, including unknowns")
    for field, item in data.items():
        if item is None:
            continue
        if not isinstance(item, str) or not item or len(item) > 256 or any(not 32 <= ord(c) <= 126 for c in item):
            raise ValueError("Bounded public HTTP validator required")
        if field == "etag" and re.fullmatch(r'(?:W/)?"[\x21\x23-\x7e]*"', item) is None:
            raise ValueError("Quoted HTTP entity tag required")
        if field == "last_modified":
            try:
                date = parsedate_to_datetime(item)
                if format_datetime(date, usegmt=True) != item:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError):
                raise ValueError("Canonical IMF-fixdate Last-Modified required") from None
    return data


def make_cache(request, snapshot, provenance, *, validators, trusted_issuers=None):
    request = _request(request)
    source = request["source"]
    refs = tuple(ResourceRef(source, identity) for identity in request["resources"])
    data = validate_observation(source, request["selection"], refs, snapshot_copy(snapshot))
    revisions = {r["source_id"]: r["source_revision"] for r in data["records"]}
    if revisions != request["revisions"]:
        raise ValueError("Incompatible cached revisions")
    p = validate_provenance(data, provenance, trusted_issuers=trusted_issuers)
    if p["context"] != request["context"]:
        raise ValueError("Provenance context mismatch")
    return {"format": FORMAT, "request": request, "snapshot": data,
            "snapshot_sha256": digest(data), "provenance": p,
            "validators": http_validators(validators), "validation": "complete"}


def validate_cache(entry, *, trusted_issuers=None):
    data = copy_metadata(entry)
    if not isinstance(data, dict) or set(data) != {
        "format", "request", "snapshot", "snapshot_sha256", "provenance", "validators", "validation"
    } or data["format"] != FORMAT or data["validation"] != "complete":
        raise ValueError("Complete versioned cache required")
    rebuilt = make_cache(data["request"], data["snapshot"], data["provenance"],
                         validators=data["validators"], trusted_issuers=trusted_issuers)
    if rebuilt != data:
        raise ValueError("Cache integrity mismatch")
    return rebuilt


def reuse_not_modified(entry, request, *, sent_validators, trusted_issuers=None):
    """Call only for a confirmed HTTP 304 from the same conditional request.

    Return a detached, unchanged B2 snapshot plus explicit status. Do not refresh
    its captured_at or interpret a mutable tag/ETag as an immutable revision.
    """
    if entry is None:
        raise ValueError("Validated cache required")
    cached = validate_cache(entry, trusted_issuers=trusted_issuers)
    if cached["provenance"]["kind"] == "historical_unknown":
        raise ValueError("Unknown historical origin cannot establish a revalidation baseline")
    request = _request(request)
    sent = http_validators(sent_validators)
    if cached["request"] != request:
        raise ValueError("Cache scope, context, resources or revisions differ")
    if all(value is None for value in sent.values()) or sent != cached["validators"]:
        raise ValueError("Matching conditional request validators required")
    return {"status": "unchanged", "snapshot": cached["snapshot"], "provenance": cached["provenance"]}
