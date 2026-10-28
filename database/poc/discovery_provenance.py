"""B4.5 additive local attestations. No collector, trust bootstrap or DB access.

HMAC authenticates an enrolled local issuer, never a provider or its response.
Issuers and verifiers must keep their shared keys outside snapshots and Git.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from contextlib import nullcontext

from discovery_cache import canonical_json, digest, validate_snapshot
from metadata_primitives import copy_metadata


FORMAT = "pepeuch-ai.discovery-provenance/v1"
KINDS = frozenset({"synthetic", "controlled_observation", "historical_unknown"})


def publication_guard(trusted_issuers):
    guard = getattr(trusted_issuers, "publication_guard", None)
    return nullcontext() if guard is None else guard()


def public_alias(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value):
        raise ValueError("Public partition or issuer alias required")
    return value


def validation_context(value):
    """Public aliases only, not credentials, usernames, URLs or HTTP headers."""
    data = copy_metadata(value)
    if not isinstance(data, dict) or set(data) != {"domain", "account_partition", "representation"}:
        raise ValueError("Exact validation context required")
    for field in data:
        public_alias(data[field])
    return data


def snapshot_copy(snapshot):
    data = copy_metadata(snapshot)
    validate_snapshot(data)
    if set(data) != {"format", "snapshot_id", "captured_at", "scope", "records"}:
        raise ValueError("Unexpected snapshot fields")
    return data


def _key(value):
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("Explicit issuer key of at least 32 bytes required")
    return value


def _mac(manifest, key):
    return hmac.new(_key(key), canonical_json(manifest).encode("utf-8"), hashlib.sha256).hexdigest()


def make_provenance(snapshot, *, kind, context, issuer=None, key=None):
    """Issuing is an explicit trust decision; this does not execute a collection.

    A production collector must own issuance AFTER successful complete validation.
    A caller with the signing key can attest false claims: HMAC cannot prevent it.
    """
    data = snapshot_copy(snapshot)
    if kind not in KINDS:
        raise ValueError("Explicit provenance category required")
    context = validation_context(context)
    if kind == "controlled_observation":
        public_alias(issuer)
        _key(key)
        # This known scope is explicitly synthetic; never promote it by signing.
        if any(isinstance(s, dict) and s.get("input") == "synthetic_fixture" for s in data["scope"].values()):
            raise ValueError("Synthetic scope cannot be attested as controlled")
    elif issuer is not None or key is not None:
        raise ValueError("Synthetic and unknown manifests are not attestations")
    manifest = {
        "format": FORMAT, "kind": kind, "snapshot_id": data["snapshot_id"],
        "snapshot_sha256": digest(data), "scope": data["scope"], "context": context,
        "issuer": issuer,
    }
    return {**manifest, "attestation": None if issuer is None else _mac(manifest, key)}


def validate_provenance(snapshot, provenance, *, trusted_issuers=None):
    """Validate binding and, for controlled data, require an independently trusted key."""
    data = snapshot_copy(snapshot)
    p = copy_metadata(provenance)
    if not isinstance(p, dict) or set(p) != {
        "format", "kind", "snapshot_id", "snapshot_sha256", "scope", "context", "issuer", "attestation"
    }:
        raise ValueError("Versioned provenance manifest required")
    if p["format"] != FORMAT or p["kind"] not in KINDS:
        raise ValueError("Unknown provenance contract")
    context = validation_context(p["context"])
    if (p["snapshot_id"] != data["snapshot_id"] or p["snapshot_sha256"] != digest(data)
            or canonical_json(p["scope"]) != canonical_json(data["scope"])):
        raise ValueError("Provenance does not bind this complete snapshot")
    if p["kind"] == "controlled_observation":
        issuer = public_alias(p["issuer"])
        key = ({} if trusted_issuers is None else trusted_issuers).get(issuer)
        if key is None:
            raise ValueError("Untrusted local issuer")
        expected = make_provenance(data, kind=p["kind"], context=context, issuer=issuer, key=key)
        if (not isinstance(p["attestation"], str) or re.fullmatch(r"[0-9a-f]{64}", p["attestation"]) is None
                or not hmac.compare_digest(p["attestation"], expected["attestation"])):
            raise ValueError("Invalid local attestation")
        authorize = getattr(trusted_issuers, "authorize_snapshot", None)
        if authorize is not None:
            authorize(issuer, data, context)
    elif p["issuer"] is not None or p["attestation"] is not None:
        raise ValueError("Unexpected attestation")
    return p


def emit_protected(snapshot, provenance, *, trusted_issuers, engine, stream):
    with publication_guard(trusted_issuers):
        return _emit_protected(snapshot, provenance, trusted_issuers=trusted_issuers, engine=engine, stream=stream)


def _emit_protected(snapshot, provenance, *, trusted_issuers, engine, stream):
    """Explicit opt-in SQL GENERATOR only. Never connects to a database.

    Buffer the entire legacy output so any rejection leaves the stream untouched.
    No fallback or automatic unwrapping of legacy/synthetic documents.
    """
    import io
    from emit_discovery_import import emit_pg, emit_surreal

    data = snapshot_copy(snapshot)
    p = validate_provenance(data, provenance, trusted_issuers=trusted_issuers)
    if p["kind"] != "controlled_observation":
        raise ValueError("Protected import requires trusted controlled provenance")
    if engine not in {"pg", "surreal"}:
        raise ValueError("Explicit import engine required")
    buffer = io.StringIO()
    (emit_pg if engine == "pg" else emit_surreal)(data, buffer)
    stream.write(buffer.getvalue())


def emit_protected_transition(before, after, *, context, trusted_issuers, engine, stream):
    with publication_guard(trusted_issuers):
        return _emit_protected_transition(before, after, context=context, trusted_issuers=trusted_issuers, engine=engine, stream=stream)


def _emit_protected_transition(before, after, *, context, trusted_issuers, engine, stream):
    """Opt-in CAS SQL generation from TWO trusted complete cache observations.

    Context is a caller-supplied target binding, NOT verification of a database
    partition. Private/multi-account storage remains unqualified and refused.
    No trust enrollment, connection, import or legacy fallback is performed.
    """
    import io
    from emit_discovery_import import emit_pg, emit_surreal
    from incremental_import_plan import plan_import
    from validated_discovery_cache import validate_cache

    context = validation_context(context)
    if context["account_partition"] != "anonymous":
        raise ValueError("Private account storage isolation is not qualified")
    current = validate_cache(after, trusted_issuers=trusted_issuers)
    previous = None if before is None else validate_cache(before, trusted_issuers=trusted_issuers)
    for entry in (current,) if previous is None else (previous, current):
        if (entry["provenance"]["kind"] != "controlled_observation"
                or entry["request"]["context"] != context):
            raise ValueError("Matching controlled provenance and explicit target context required")
    if engine not in {"pg", "surreal"}:
        raise ValueError("Explicit import engine required")
    plan_import(previous, current, trusted_issuers=trusted_issuers)
    output = io.StringIO()
    (emit_pg if engine == "pg" else emit_surreal)(
        current["snapshot"], output, expected_snapshot=None if previous is None else previous["snapshot"])
    stream.write(output.getvalue())
