"""B3.3: MoArk's served-model roster, never a repository/weights contract.

Official shape: https://moark.ai/v1/yaml, GET /models, model.list.
Pure normalization; no inference, authentication, network or database writes.
"""

from __future__ import annotations

import re
from typing import Any

from source_adapters import SourceRecord
from metadata_primitives import copy_metadata as _json_copy


API_BASE = "https://moark.ai/v1"
CATALOG_URL = API_BASE + "/models?type=text2text&include_details=false"


def model_id(value: Any) -> str:
    # An opaque provider ID, not an owner/name repository or a canonical model.
    if (not isinstance(value, str) or len(value) > 256
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError("Invalid MoArk model ID")
    return value


def normalize_moark_model(data: dict[str, Any], *, requested_id: str) -> SourceRecord:
    """Normalize a model.list entry in the fixed official moark.ai API scope.

    created is a timestamp, owned_by a vendor label; neither proves revision,
    authorship, upstream identity, downloadable weights or inference rights.
    """
    requested_id = model_id(requested_id)
    if not isinstance(data, dict) or data.get("object") != "model":
        raise ValueError("MoArk entry must be a model object")
    raw = _json_copy(data)
    if model_id(raw.get("id")) != requested_id:
        raise ValueError("MoArk model ID differs from requested ID")
    created = raw.get("created")
    if created is not None and (isinstance(created, bool) or not isinstance(created, int) or created < 0):
        raise ValueError("MoArk created must be a nonnegative integer or null")
    owner = raw.get("owned_by")
    if owner is not None and (not isinstance(owner, str) or not owner.strip()):
        raise ValueError("MoArk owned_by must be nonempty text or null")
    return SourceRecord(
        source="moark", source_id=requested_id, source_revision=None,
        entity_type="inference_endpoint", display_name=requested_id,
        attributes={
            "api_base": API_BASE,
            "catalog_url": CATALOG_URL,
            "owned_by": owner,
            "created": created,
            "access": "unknown",
            "license": None,
            "weights_available": None,
        },
        relationships=(), raw_metadata=raw,
    )


def select_moark_model(data: dict[str, Any], *, requested_id: str) -> SourceRecord:
    """Select exactly one ID; reject missing IDs, invalid envelopes or duplicates.

    No prefix/name matching, no automatic cross-platform relationship, and no
    arbitrary choice when the roster repeats an ID (even with equal content).
    """
    requested_id = model_id(requested_id)
    if not isinstance(data, dict) or data.get("object") != "list" or not isinstance(data.get("data"), list):
        raise ValueError("MoArk response must be a model list")
    raw = _json_copy(data)
    # A future pagination contract must be implemented before claiming absence.
    if (raw.get("has_more") is not None and raw["has_more"] is not False
            or raw.get("next") is not None or raw.get("next_page") is not None):
        raise ValueError("Unexpected paginated MoArk response")
    selected = None
    seen = set()
    for item in raw["data"]:
        if not isinstance(item, dict) or item.get("object") != "model":
            raise ValueError("MoArk roster contains a non-model entry")
        identity = model_id(item.get("id"))
        if identity in seen:
            raise ValueError("Duplicate MoArk model ID")
        seen.add(identity)
        if identity == requested_id:
            selected = item
    if selected is None:
        raise ValueError("Requested MoArk model not observed in this public roster")
    return normalize_moark_model(selected, requested_id=requested_id)
