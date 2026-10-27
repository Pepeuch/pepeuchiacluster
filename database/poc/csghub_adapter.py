"""B3.2: normalize CSGHub's *model repository* metadata into SourceRecord.

The input is the JSON model-info payload returned by the official CSGHub SDK's
metadata GET path. No downloading, inference, authentication or DB access.
CSGHub, Hugging Face, and ModelScope remain separate identity namespaces.
"""

from __future__ import annotations

import re
from typing import Any

from source_adapters import SourceRecord
from metadata_primitives import copy_metadata, optional_nonnegative_int


_REPO_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


def model_id(value: Any) -> str:
    if not isinstance(value, str) or value.count("/") != 1:
        raise ValueError("CSGHub model ID must be namespace/name")
    if not all(_REPO_PART.fullmatch(part) and part not in (".", "..")
               for part in value.split("/")):
        raise ValueError("Invalid CSGHub model namespace/name")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"CSGHub {field} must be text or null")
    return value if value.strip() else None


def _optional_count(value: Any, field: str) -> int | None:
    return optional_nonnegative_int(value, f"CSGHub {field}")


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"CSGHub {field} must be boolean or null")
    return value


def _gating(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return ("gated" if value else "not_gated"), None
    if value in ("auto", "manual"):
        return "gated", value
    raise ValueError("Unexpected CSGHub gated value")


def normalize_csghub_model(data: dict[str, Any], *, requested_id: str) -> SourceRecord:
    """Normalize one CSGHub model-info response, never extrapolating from tags."""
    requested_id = model_id(requested_id)
    if not isinstance(data, dict):
        raise ValueError("CSGHub model metadata must be an object")
    # Keep raw metadata JSON-native and reject NaN, infinity, or custom types.
    raw = copy_metadata(data)
    if model_id(raw.get("id")) != requested_id:
        raise ValueError("CSGHub response ID differs from requested model")

    if raw.get("repo_type") not in (None, "model"):
        raise ValueError("CSGHub response is not a model repository")

    private = _optional_bool(raw.get("private"), "private")
    gating, approval_mode = _gating(raw.get("gated"))
    visibility = "unknown" if private is None else ("private" if private else "public")
    # An explicitly public listing does not prove that downloads are ungated.
    access = ("private" if private is True else
              "gated" if gating == "gated" else
              "public" if private is False and gating == "not_gated" else
              "unknown")

    sha = _optional_string(raw.get("sha"), "sha")
    revision = sha.lower() if sha is not None and _SHA.fullmatch(sha) else None
    tags = raw.get("tags")
    if tags is not None and (
        not isinstance(tags, list) or
        any(not isinstance(t, str) or not t.strip() for t in tags)
    ):
        raise ValueError("CSGHub tags must be a list of nonempty strings or null")

    files: list[str] | None = None
    if raw.get("siblings") is not None:
        if not isinstance(raw["siblings"], list):
            raise ValueError("CSGHub siblings must be an array or null")
        files = []
        for entry in raw["siblings"]:
            if not isinstance(entry, dict):
                raise ValueError("CSGHub sibling must be an object")
            path = _optional_string(entry.get("rfilename"), "siblings[].rfilename")
            if not path:
                raise ValueError("CSGHub sibling missing filename")
            files.append(path)

    # Positive evidence from repository file names only; an absent listing is
    # unknown, not proof that a format is unavailable.
    formats = []
    if files is not None:
        for extension in ("gguf", "safetensors"):
            if any(path.lower().endswith("." + extension) for path in files):
                formats.append(extension)

    card = raw.get("cardData")
    if card is not None and not isinstance(card, dict):
        raise ValueError("CSGHub cardData must be an object or null")
    license_name = _optional_string(raw.get("license"), "license")
    card_license = (_optional_string(card.get("license"), "cardData.license")
                    if isinstance(card, dict) else None)
    if license_name is not None and card_license is not None and license_name != card_license:
        raise ValueError("Conflicting CSGHub license declarations")
    license_name = license_name or card_license

    return SourceRecord(
        source="csghub", source_id=requested_id, source_revision=revision,
        entity_type="model_artifact", display_name=requested_id.rsplit("/", 1)[-1],
        attributes={
            "visibility": visibility,
            "access": access,
            "gated": None if gating is None else gating == "gated",
            "approval_mode": approval_mode,
            "license": license_name,
            "author": _optional_string(raw.get("author"), "author"),
            "pipeline_tag": _optional_string(raw.get("pipeline_tag"), "pipeline_tag"),
            "library_name": _optional_string(raw.get("library_name"), "library_name"),
            "tags": tags,
            "downloads": _optional_count(raw.get("downloads"), "downloads"),
            "likes": _optional_count(raw.get("likes"), "likes"),
            "created_at": _optional_string(raw.get("created_at"), "created_at"),
            "last_modified": _optional_string(raw.get("last_modified"), "last_modified"),
            "file_count": len(files) if files is not None else None,
            "observed_formats": formats if files is not None else None,
            # Explicit model card only. Bare "apache-2.0" tags are ambiguous;
            # do not silently promote them to a verified license statement.
        },
        relationships=(), raw_metadata=raw,
    )
