"""B3.1: normalize ModelScope *model repository metadata* into SourceRecord.

Input is the official modelscope-hub RepoInfo.to_dict() shape, not a model
weights file, an inference endpoint, a Studio, or an agent. No network/DB I/O.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
import json
import re
from typing import Any

from source_adapters import SourceRecord


_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_SECRET_KEYS = {"api_key", "api_token", "access_token", "authorization", "credentials", "password", "secret", "token"}


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Unsupported ModelScope metadata type: {type(value).__name__}")


def _secret_free(value: Any) -> None:
    if isinstance(value, dict):
        for name, child in value.items():
            if not isinstance(name, str):
                raise ValueError("ModelScope metadata keys must be strings")
            if name.lower() in _SECRET_KEYS:
                raise ValueError("Refusing credential-like ModelScope metadata")
            _secret_free(child)
    elif isinstance(value, list):
        for item in value:
            _secret_free(item)


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or value.count("/") != 1:
        raise ValueError("ModelScope repository identity must be owner/name")
    owner, name = value.split("/", 1)
    if any(not part or part in (".", "..") or any(c.isspace() or ord(c) < 32 for c in part)
           for part in (owner, name)):
        raise ValueError("Invalid ModelScope owner/name")
    return value


def _string_or_none(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"ModelScope {field} must be text or null")
    return value if value.strip() else None


def _timestamp_or_none(value: Any) -> str | int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("ModelScope last_modified must be text, epoch timestamp or null")
    return value


def _nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"ModelScope {field} must be a nonnegative integer or null")
    return value


def _visibility(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        raise ValueError("ModelScope visibility cannot be a boolean")
    if isinstance(value, int):
        mapping = {1: "private", 3: "internal", 5: "public"}
        return mapping.get(value, "unknown")
    if isinstance(value, str):
        return value.lower() if value.lower() in ("public", "private", "internal") else "unknown"
    raise ValueError("Unexpected ModelScope visibility type")


def normalize_modelscope_repo(data: dict[str, Any], *, requested_id: str) -> SourceRecord:
    """A read-only model repository contract; no cross-hub identity guesses.

    The SDK's `get_repo(..., repo_type='model')` currently does not pin a
    requested revision. Record only a full explicit commit hash as revision.
    """
    requested_id = _identifier(requested_id)
    if not isinstance(data, dict):
        raise ValueError("ModelScope RepoInfo must be an object")
    _secret_free(data)
    # Ensure raw_metadata stays JSON-safe without stringifying unknown objects.
    raw = json.loads(json.dumps(data, allow_nan=False, ensure_ascii=False, default=_json_default))

    repository_type = raw.get("repo_type")
    if repository_type is not None and repository_type != "model":
        raise ValueError("ModelScope response is not a model repository")

    resolved_id = raw.get("repo_id")
    if resolved_id is None and isinstance(raw.get("id"), str) and "/" in raw["id"]:
        resolved_id = raw["id"]
    if resolved_id is None and isinstance(raw.get("owner"), str) and isinstance(raw.get("name"), str):
        resolved_id = raw["owner"] + "/" + raw["name"]
    if _identifier(resolved_id) != requested_id:
        raise ValueError("ModelScope repository ID does not match the requested model")

    gated = raw.get("gated")
    if gated is not None and not isinstance(gated, bool):
        raise ValueError("ModelScope gated must be a boolean or null")
    private = raw.get("private")
    if private is not None and not isinstance(private, bool):
        raise ValueError("ModelScope private must be a boolean or null")
    visibility = _visibility(raw.get("visibility"))
    if visibility == "unknown" and private is not None:
        visibility = "private" if private else "public"
    if private is not None and visibility in ("public", "private") and private != (visibility == "private"):
        raise ValueError("Conflicting ModelScope private and visibility values")
    if gated is True and visibility == "public":
        raise ValueError("Conflicting public and gated ModelScope metadata")

    tags = raw.get("tags")
    if tags is not None and (not isinstance(tags, list) or
                             any(not isinstance(item, str) or not item.strip() for item in tags)):
        raise ValueError("ModelScope tags must be a list of nonempty strings or null")

    # A last_modified timestamp, a branch name and a numeric DB id are NOT
    # immutable source revisions. Preserve those only as raw/attributes.
    commit = raw.get("sha", raw.get("commit_sha"))
    if commit is not None and not isinstance(commit, str):
        raise ValueError("ModelScope commit hash must be text or null")
    source_revision = commit.lower() if commit is not None and _COMMIT.fullmatch(commit) else None
    last_modified = _timestamp_or_none(raw.get("last_modified"))
    declared_name = _string_or_none(raw.get("display_name"), "display_name")
    display_name = declared_name or requested_id.rsplit("/", 1)[-1]

    return SourceRecord(
        source="modelscope", source_id=requested_id, source_revision=source_revision,
        entity_type="model_artifact", display_name=display_name,
        attributes={
            "visibility": visibility,
            "gated": gated,
            "access": "gated" if gated is True else visibility,
            "license": _string_or_none(raw.get("license"), "license"),
            "description": _string_or_none(raw.get("description"), "description"),
            "tags": tags,
            "downloads": _nonnegative_int(raw.get("downloads"), "downloads"),
            "likes": _nonnegative_int(raw.get("likes"), "likes"),
            "last_modified": last_modified,
            "revision_label": _string_or_none(raw.get("revision"), "revision"),
            # Missing file data must not imply an empty repository.
            "files": None,
        },
        relationships=(), raw_metadata=raw,
    )
