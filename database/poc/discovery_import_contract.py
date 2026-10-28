"""Engine-neutral transition checks, without revision ordering or DB access."""

from datetime import datetime

from discovery_cache import canonical_json, compare_snapshots, validate_snapshot
from metadata_primitives import copy_metadata


def validate_transition(before, after):
    """Return detached B2 observations; compare dates as exact aware instants.

    captured_at orders observations, NOT provider revisions. Never rewrite the
    original timestamp or infer an order from a tag, SHA or source revision.
    """
    current = copy_metadata(after)
    validate_snapshot(current)
    if before is None:
        return None, current
    previous = copy_metadata(before)
    validate_snapshot(previous)
    compare_snapshots(previous, current)  # Includes JSON-type-sensitive scope.
    old_time = datetime.fromisoformat(previous["captured_at"].replace("Z", "+00:00"))
    new_time = datetime.fromisoformat(current["captured_at"].replace("Z", "+00:00"))
    if new_time < old_time:
        raise ValueError("Older capture cannot replace a newer baseline")
    if new_time == old_time:
        old_content = {k: v for k, v in previous.items() if k != "captured_at"}
        new_content = {k: v for k, v in current.items() if k != "captured_at"}
        if canonical_json(old_content) != canonical_json(new_content):
            raise ValueError("Conflicting observations at the same capture time")
    return previous, current
