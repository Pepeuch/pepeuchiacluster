#!/usr/bin/env python3
"""Build a bounded B2 discovery snapshot from the existing source adapters.

Default: local pinned models.dev only (no network). --include-online reads
the same bounded public endpoints as B1, never downloads weights or writes DBs.
The JSON snapshot goes to stdout; status goes to stderr.
"""

from __future__ import annotations

from metadata_primitives import error_summary, strict_json_loads

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.error import HTTPError
from urllib.parse import quote, urlencode

from discovery_cache import make_snapshot
from import_models_dev import DEFAULT_SOURCE_ROOT, COPY_COLUMNS, make_row, source_commit
from probe_source_adapters import (
    AGENTS_REPO, HF_MODELS, NIM_RESOURCE, NIM_TAG, get_json,
)
from source_adapters import (
    SourceRecord, normalize_awesome_catalog, normalize_huggingface_model,
    normalize_nvidia_nim_metadata,
)


def collect_modelsdev(source_root: Path, *, commit: str, limit: int) -> list[SourceRecord]:
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    paths = sorted((source_root / "models").rglob("*.toml"))
    if not paths:
        raise ValueError("No models.dev TOML files")
    if limit:
        paths = paths[:limit]
    records = []
    for path in paths:
        row = dict(zip(COPY_COLUMNS, make_row(source_root, path, commit), strict=True))
        raw_metadata = strict_json_loads(row["raw_metadata"])
        records.append(SourceRecord(
            source="models.dev", source_id=row["model_id"],
            source_revision=commit, entity_type="model_reference",
            display_name=row["display_name"],
            attributes={
                "source_path": row["source_path"],
                "family": row["family"] or None,
                "open_weights": bool_or_none(row["open_weights"]),
                "context_tokens": row["context_tokens"] if row["context_tokens"] != "" else None,
                "tools_supported": bool_or_none(row["tools_supported"]),
                "weights_count": row["weights_count"],
                "benchmarks_count": row["benchmarks_count"],
            },
            relationships=(), raw_metadata=raw_metadata,
        ))
    return records


def bool_or_none(value: str) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "":
        return None
    raise ValueError("Unexpected normalized models.dev boolean")


def collect_online(*, timeout: int, agent_limit: int) -> tuple[list[SourceRecord], dict]:
    if agent_limit < 0:
        raise ValueError("agent_limit must be nonnegative")
    records = []
    for model_id in HF_MODELS:
        raw = get_json(f"https://huggingface.co/api/models/{quote(model_id, safe='/')}", timeout)
        record = normalize_huggingface_model(raw)
        if record.source_id != model_id:
            raise ValueError("Hugging Face API identity mismatch")
        records.append(record)

    response = get_json(f"https://api.github.com/repos/{AGENTS_REPO}/commits/main", timeout)
    commit = response.get("sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Could not pin agent catalog commit")
    raw_agents = get_json(
        f"https://raw.githubusercontent.com/{AGENTS_REPO}/{commit}/awesome-agents.json", timeout
    )
    agents = normalize_awesome_catalog(raw_agents, source_commit=commit)
    # Sampling happens AFTER complete deduplication/validation.
    records.extend(agents[:agent_limit] if agent_limit else agents)

    # NVIDIA publishes metadata per exact container tag; 404 is normal.
    metadata_status = "available"
    query = urlencode({"resourceId": NIM_RESOURCE, "tag": NIM_TAG})
    try:
        nim_raw = get_json(f"https://api.ngc.nvidia.com/v2/nim/metadata?{query}", timeout)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        metadata_status = "unavailable_for_tag"
    else:
        records.append(normalize_nvidia_nim_metadata(nim_raw, resource_id=NIM_RESOURCE, tag=NIM_TAG))

    scope = {
        "huggingface": {"mode": "exact_ids", "ids": list(HF_MODELS)},
        "awesome-ai-agents": {"mode": "first_n_unique", "limit": agent_limit},
        "nvidia-nim-metadata": {"mode": "exact_tag", "resource_id": NIM_RESOURCE,
                                "tag": NIM_TAG},
    }
    if metadata_status != "available":
        print("NVIDIA metadata unavailable for selected tag; no NIM record added", file=sys.stderr)
    return records, scope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--models-limit", type=int, default=5,
                        help="First N sorted models.dev files; 0 = all (default: 5)")
    parser.add_argument("--include-online", action="store_true",
                        help="Also sample public HF, Awesome AI Agents and NVIDIA NIM APIs")
    parser.add_argument("--agents-limit", type=int, default=3,
                        help="First N distinct agents; 0 = all (default: 3)")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    if args.models_limit < 0 or args.agents_limit < 0 or not 1 <= args.timeout <= 60:
        parser.error("Limits must be >= 0 and timeout between 1 and 60 seconds")
    try:
        root = args.source_root.resolve()
        commit = source_commit(root)  # Refuses dirty/unpinned source checkout.
        records = collect_modelsdev(root, commit=commit, limit=args.models_limit)
        scope = {"models.dev": {"mode": "first_n_sorted", "limit": args.models_limit}}
        if args.include_online:
            online, online_scope = collect_online(timeout=args.timeout, agent_limit=args.agents_limit)
            records.extend(online)
            scope.update(online_scope)
        snapshot = make_snapshot(records, scope=scope)
    except (OSError, ValueError, TypeError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as exc:
        print(error_summary("Discovery collection", exc), file=sys.stderr)
        return 1
    print(f"Prepared {len(snapshot['records'])} cache entries; snapshot {snapshot['snapshot_id']}", file=sys.stderr)
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
