"""B2 POC: deterministic, database-independent discovery snapshot contract.

The cache indexes external resources. It is NOT the personal model catalog,
and no source names are resolved into a guessed canonical model identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable

from source_adapters import SourceRecord
from metadata_primitives import copy_metadata


FORMAT = "pepeuch-ai.discovery-cache/v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def record_key(source: str, entity_type: str, source_id: str) -> str:
    return "d_" + digest([source, entity_type, source_id])


def record_payload(record: SourceRecord) -> dict[str, Any]:
    return copy_metadata({
        "source": record.source,
        "entity_type": record.entity_type,
        "source_id": record.source_id,
        "source_revision": record.source_revision,
        "display_name": record.display_name,
        "attributes": record.attributes,
        "relationships": list(record.relationships),
        "raw_metadata": record.raw_metadata,
    })


def _record_from_payload(payload: dict[str, Any]) -> SourceRecord:
    if not isinstance(payload, dict):
        raise ValueError("Cache record payload must be an object")
    for field in ("source", "entity_type", "source_id", "display_name"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"Cache record missing {field}")
    if payload["entity_type"] not in (
        "model_reference", "model_artifact", "agent_resource", "nim_microservice", "inference_endpoint"
    ):
        raise ValueError("Unknown discovery entity type")
    if payload.get("source_revision") is not None and not isinstance(payload["source_revision"], str):
        raise ValueError("Invalid source_revision")
    if not isinstance(payload.get("attributes"), dict) or not isinstance(payload.get("raw_metadata"), dict):
        raise ValueError("Attributes and raw metadata must be objects")
    relations = payload.get("relationships")
    if not isinstance(relations, list) or any(
        not isinstance(x, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in x.items())
        for x in relations
    ):
        raise ValueError("Relationships must be objects with string keys and values")
    # model_reference is B2's local normalized models.dev type; SourceRecord
    # accepts its string at runtime, without imposing a database schema.
    return SourceRecord(
        source=payload["source"], source_id=payload["source_id"],
        source_revision=payload.get("source_revision"), entity_type=payload["entity_type"],
        display_name=payload["display_name"], attributes=payload["attributes"],
        relationships=tuple(relations), raw_metadata=payload["raw_metadata"],
    )


def make_snapshot(
    records: Iterable[SourceRecord], *, scope: dict[str, Any], captured_at: str | None = None,
) -> dict[str, Any]:
    if not isinstance(scope, dict) or not scope:
        raise ValueError("A declared collection scope is required")
    scope = copy_metadata(scope)
    if captured_at is None:
        captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _validate_time(captured_at)

    by_key = {}
    for record in records:
        payload = record_payload(record)
        _record_from_payload(payload)
        key = record_key(record.source, record.entity_type, record.source_id)
        entry = {"record_key": key, "payload_sha256": digest(payload), **payload}
        prior = by_key.get(key)
        if prior is not None and prior != entry:
            raise ValueError(f"Conflicting records for {record.source}/{record.source_id}")
        by_key[key] = entry
    if not by_key:
        raise ValueError("Refusing an empty discovery snapshot")

    entries = [by_key[key] for key in sorted(by_key)]
    signature = [
        [entry["record_key"], entry["payload_sha256"]] for entry in entries
    ]
    return {
        "format": FORMAT,
        "snapshot_id": "s_" + digest({"scope": scope, "content": signature}),
        "captured_at": captured_at,
        "scope": scope,
        "records": entries,
    }


def _validate_time(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("captured_at must be an ISO8601 timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid captured_at timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("captured_at must include timezone")


def validate_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("Unknown discovery snapshot format")
    if set(data) != {"format", "snapshot_id", "captured_at", "scope", "records"}:
        raise ValueError("Exact discovery snapshot envelope required")
    # make_snapshot may choose a date when creating a NEW observation. A reader
    # must never silently invent one for a missing/null persisted observation.
    _validate_time(data["captured_at"])
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("Snapshot records must be a list")
    recovered = []
    for entry in records:
        if not isinstance(entry, dict) or not isinstance(entry.get("record_key"), str):
            raise ValueError("Malformed discovery record")
        if not entry["record_key"].startswith("d_") or not HEX64.fullmatch(entry["record_key"][2:]):
            raise ValueError("Malformed record key")
        if not isinstance(entry.get("payload_sha256"), str) or not HEX64.fullmatch(entry["payload_sha256"]):
            raise ValueError("Malformed payload digest")
        payload = {k: v for k, v in entry.items() if k not in ("record_key", "payload_sha256")}
        # Unknown top-level keys must not silently bypass the digest contract.
        if set(payload) != set(record_payload(_record_from_payload(payload))):
            raise ValueError("Unexpected discovery payload fields")
        if digest(payload) != entry["payload_sha256"]:
            raise ValueError("Discovery payload digest mismatch")
        record = _record_from_payload(payload)
        if record_key(record.source, record.entity_type, record.source_id) != entry["record_key"]:
            raise ValueError("Discovery identity mismatch")
        recovered.append(record)
    expected = make_snapshot(recovered, scope=data.get("scope"), captured_at=data.get("captured_at"))
    if data.get("snapshot_id") != expected["snapshot_id"] or records != expected["records"]:
        raise ValueError("Discovery snapshot integrity or ordering mismatch")
    return data


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    validate_snapshot(before)
    validate_snapshot(after)
    if canonical_json(before["scope"]) != canonical_json(after["scope"]):
        raise ValueError("Different collection scopes; cannot interpret missing records")
    old = {x["record_key"]: x for x in before["records"]}
    new = {x["record_key"]: x for x in after["records"]}
    common = old.keys() & new.keys()
    return {
        "before": before["snapshot_id"],
        "after": after["snapshot_id"],
        "added": sorted(new.keys() - old.keys()),
        "changed": sorted(k for k in common if old[k]["payload_sha256"] != new[k]["payload_sha256"]),
        "not_observed": sorted(old.keys() - new.keys()),
        "unchanged_count": sum(old[k]["payload_sha256"] == new[k]["payload_sha256"] for k in common),
        "note": "not_observed is NOT a deletion instruction (sample or source may be partial)",
    }
