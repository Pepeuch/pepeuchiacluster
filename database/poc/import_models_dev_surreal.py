#!/usr/bin/env python3
"""Generate an idempotent SurrealQL import of the pinned models.dev snapshot.

Requires only Python's standard library and the existing PostgreSQL POC
importer's TOML parsing helpers. Output goes to stdout; diagnostics to stderr.
Nothing is written to the database by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any, TextIO

from import_models_dev import (
    COPY_COLUMNS,
    DEFAULT_SOURCE_ROOT,
    SOURCE_NAME,
    make_row,
    source_commit,
)


def _nullable_bool(value: str) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "":
        return None
    raise ValueError(f"Unexpected CSV boolean value: {value!r}")


def record_id(record: dict[str, Any]) -> str:
    """Fixed, unquoted SurrealDB identifier, unique per source/snapshot/path."""
    key = "\x00".join(
        (record["source"], record["source_commit"], record["source_path"])
    )
    return "m_" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def make_record(row: list[Any]) -> dict[str, Any]:
    values = dict(zip(COPY_COLUMNS, row, strict=True))
    return {
        "source": values["source"],
        "source_commit": values["source_commit"],
        "source_path": values["source_path"],
        "model_id": values["model_id"],
        "display_name": values["display_name"],
        "family": values["family"],
        "open_weights": _nullable_bool(values["open_weights"]),
        "context_tokens": (
            values["context_tokens"]
            if values["context_tokens"] != "" else None
        ),
        "tools_supported": _nullable_bool(values["tools_supported"]),
        "weights_count": values["weights_count"],
        "benchmarks_count": values["benchmarks_count"],
        "raw_metadata": json.loads(values["raw_metadata"]),
    }


def emit_surql(records: list[dict[str, Any]], output: TextIO) -> None:
    # Required by the /import endpoint since SurrealDB 3.0.4. With this flag,
    # import skips events/side effects. Do not send to /sql for this POC.
    output.write("OPTION IMPORT;\n")
    output.write("-- models.dev pinned snapshot; safe to import repeatedly.\n")
    output.write("-- Every record has an ID derived from source, commit and path.\n")
    for record in records:
        payload = json.dumps(
            record, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        output.write(
            f"UPSERT external_models:{record_id(record)} "
            f"CONTENT {payload} RETURN NONE;\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=DEFAULT_SOURCE_ROOT,
        help="Checked-out models.dev git submodule",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Generate first N sorted TOML files (default: all)",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must not be negative")

    root = args.source_root.resolve()
    models_dir = root / "models"
    if not models_dir.is_dir():
        parser.error(f"No models/ directory at {root}; initialize the submodule")

    try:
        commit = source_commit(root)
        paths = sorted(models_dir.rglob("*.toml"))
        if args.limit:
            paths = paths[:args.limit]
        if not paths:
            raise ValueError("No TOML models found")
        records = [make_record(make_row(root, path, commit)) for path in paths]
        keys = [record_id(record) for record in records]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate SurrealDB record IDs")
    except (
        OSError, ValueError, TypeError, subprocess.CalledProcessError,
        tomllib.TOMLDecodeError,
    ) as exc:
        print(f"Import preparation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Prepared {len(records)} SurrealDB records from {commit}", file=sys.stderr)
    emit_surql(records, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
