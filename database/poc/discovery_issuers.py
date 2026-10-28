"""Explicit local issuer authority. No key files, bootstrap, network or DB.

An alias names one key generation; revoked aliases are never reused. Holding
publication_guard linearizes verification/publication against other-thread revoke.
The owner of this in-memory authority remains a trusted local administrator.
"""

from collections.abc import Mapping
from contextlib import contextmanager
import hmac
from threading import RLock

from discovery_cache import canonical_json
from discovery_provenance import public_alias, validation_context
from source_spec_design import SOURCE_SPECS


class IssuerRegistry(Mapping):
    def __init__(self):
        self._lock = RLock()
        self._entries = {}

    def __repr__(self):
        return "IssuerRegistry(keys=redacted)"

    @contextmanager
    def publication_guard(self):
        with self._lock:
            yield

    def __iter__(self):
        with self._lock:
            return iter(tuple(k for k, v in self._entries.items() if v["active"]))

    def __len__(self):
        with self._lock:
            return sum(v["active"] for v in self._entries.values())

    def __getitem__(self, issuer):
        with self._lock:
            entry = self._entries.get(issuer)
            if entry is None or not entry["active"]:
                raise KeyError("Unknown or revoked local issuer")
            return entry["key"]

    def enroll(self, issuer, key, *, grants):
        issuer = public_alias(issuer)
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("Explicit issuer key of at least 32 bytes required")
        permitted = set()
        for grant in grants:
            if (not isinstance(grant, dict) or set(grant) != {"source", "context"}
                    or grant["source"] not in SOURCE_SPECS):
                raise ValueError("Exact source/context grant required")
            permitted.add((grant["source"], canonical_json(validation_context(grant["context"]))))
        if not permitted:
            raise ValueError("At least one explicit issuer grant required")
        with self._lock:
            if issuer in self._entries:
                raise ValueError("Issuer alias cannot be reused")
            if any(hmac.compare_digest(entry["key"], key) for entry in self._entries.values()):
                raise ValueError("Issuer key generation cannot be reused under another alias")
            self._entries[issuer] = {"key": key, "active": True, "grants": frozenset(permitted)}

    def revoke(self, issuer):
        issuer = public_alias(issuer)
        with self._lock:
            if issuer not in self._entries:
                raise ValueError("Unknown issuer cannot be revoked")
            self._entries[issuer]["active"] = False

    def rotate(self, issuer, new_issuer, new_key):
        with self._lock:
            self[issuer]  # Requires a currently active generation.
            grants = self._entries[issuer]["grants"]
            import json
            self.enroll(new_issuer, new_key, grants=[{"source": s, "context": json.loads(c)} for s, c in grants])
            self._entries[issuer]["active"] = False

    def authorize(self, issuer, source, context, *, key=None):
        issuer = public_alias(issuer)
        context = validation_context(context)
        with self._lock:
            try:
                active_key = self[issuer]
            except KeyError:
                raise ValueError("Unknown or revoked local issuer") from None
            if (source, canonical_json(context)) not in self._entries[issuer]["grants"]:
                raise ValueError("Issuer is not authorized for this source/context")
            if key is not None and (not isinstance(key, bytes) or not hmac.compare_digest(active_key, key)):
                raise ValueError("Issuer key generation does not match")
            return active_key

    def authorize_snapshot(self, issuer, snapshot, context):
        with self._lock:
            sources = {r["source"] for r in snapshot["records"]}
            if set(snapshot["scope"]) != sources:
                raise ValueError("Issuer requires an exact registered source scope")
            for source in sources:
                self.authorize(issuer, source, context)
