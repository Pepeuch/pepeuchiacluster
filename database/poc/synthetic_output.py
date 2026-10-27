"""Opt-in fixture envelope rejected by unchanged B2 import generators."""

from __future__ import annotations

from typing import Any

from discovery_cache import validate_snapshot
from metadata_primitives import copy_metadata


def protect_fixture_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Preserve every B2 byte/value inside an explicitly synthetic container.

    Old importers reject its outer format before emitting SQL. This is not
    proof of authenticity and cannot protect an intentionally unwrapped copy
    or the historical raw B2 fixture mode. No automatic unwrapping is provided.
    """
    inner = copy_metadata(snapshot)
    validate_snapshot(inner)
    return {"format": "pepeuch-ai.synthetic-discovery/v1", "synthetic": True,
            "importable_as_real_observation": False, "snapshot": inner}
