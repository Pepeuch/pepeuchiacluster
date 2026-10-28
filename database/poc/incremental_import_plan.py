"""Review-only incremental import preconditions. No SQL emission or DB execution.

B2 generators now have a separate capture-time guard. They do not execute this
plan's expected-state CAS or establish provider revision ordering/partitions.
The legacy_generators_guarded field concerns this complete CAS protocol only.
"""

from discovery_cache import compare_snapshots
from metadata_primitives import copy_metadata
from discovery_import_contract import validate_transition
from validated_discovery_cache import validate_cache


def plan_import(before, after, *, trusted_issuers=None):
    after = validate_cache(after, trusted_issuers=trusted_issuers)
    before = None if before is None else validate_cache(before, trusted_issuers=trusted_issuers)
    if after["provenance"]["kind"] == "historical_unknown" or before is not None and before["provenance"]["kind"] == "historical_unknown":
        raise ValueError("Unknown historical origin cannot establish incremental import preconditions")
    if before is not None:
        for key in ("source", "selection", "context"):
            if before["request"][key] != after["request"][key]:
                raise ValueError("Partition or selection changes need a separate reviewed baseline")
        if before["provenance"]["kind"] != after["provenance"]["kind"]:
            raise ValueError("Synthetic and controlled baselines cannot be mixed")
        previous, current = validate_transition(before["snapshot"], after["snapshot"])
        changes = compare_snapshots(previous, current)
        old = {r["record_key"]: r for r in previous["records"]}
    else:
        current = after["snapshot"]
        old = {}
        changes = {"added": sorted(r["record_key"] for r in current["records"]), "changed": [], "not_observed": []}
    actions = []
    for record in current["records"]:
        previous_record = old.get(record["record_key"])
        expected = None if previous_record is None else {
            "payload_sha256": previous_record["payload_sha256"],
            "last_seen_snapshot": before["snapshot"]["snapshot_id"],
            "last_seen_at": before["snapshot"]["captured_at"],
        }
        actions.append({"operation": "upsert_if_expected_or_already_applied", "expected": expected,
                        "record": {**record, "last_seen_snapshot": current["snapshot_id"], "last_seen_at": current["captured_at"]}})
    return copy_metadata({"format": "pepeuch-ai.incremental-import-plan/v1", "executable": False,
                          "data_kind": after["provenance"]["kind"], "scope": current["scope"],
                          "context": after["request"]["context"], "snapshot_id": current["snapshot_id"],
                          "changes": changes, "actions": actions, "delete_actions": [],
                          "requires": ["current_database_state_check", "atomic_compare_and_swap_or_staging",
                                       "engine_specific_failure_replay_tests", "account_domain_storage_isolation_decision"],
                          "legacy_generators_guarded": False})
