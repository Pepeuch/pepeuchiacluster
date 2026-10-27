#!/usr/bin/env python3
"""Emit PG or SurrealDB idempotent imports from ONE validated B2 snapshot.

The generator never opens a DB connection. Imports only update the separate
discovery cache. Missing entries are never deleted by an import.
"""

from __future__ import annotations

from metadata_primitives import error_summary, strict_json_loads

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from discovery_cache import canonical_json, validate_snapshot


PG_COLUMNS = (
    "record_key", "source", "entity_type", "source_id", "source_revision", "display_name",
    "attributes", "relationships", "raw_metadata", "payload_sha256",
    "last_seen_snapshot", "last_seen_at",
)


def import_record(entry: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        **entry,
        "last_seen_snapshot": snapshot["snapshot_id"],
        "last_seen_at": snapshot["captured_at"],
    }


def emit_pg(snapshot: dict[str, Any], stream: TextIO) -> None:
    validate_snapshot(snapshot)
    stream.write("BEGIN;\n")
    stream.write(
        "CREATE TEMP TABLE _discovery_stage "
        "(LIKE poc.discovery_cache INCLUDING DEFAULTS) ON COMMIT DROP;\n"
    )
    columns = ", ".join(PG_COLUMNS)
    stream.write(f"COPY _discovery_stage ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true);\n")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(PG_COLUMNS)
    for entry in snapshot["records"]:
        record = import_record(entry, snapshot)
        # COPY FROM STDIN has a special end marker \. ; never permit a raw
        # text field to introduce an independent physical line of that form.
        for field in ("source", "entity_type", "source_id", "source_revision", "display_name"):
            value = record.get(field)
            if isinstance(value, str) and ("\n" in value or "\r" in value):
                raise ValueError(f"Multiline discovery field not allowed: {field}")
        values = [
            canonical_json(record[field]) if field in ("attributes", "relationships", "raw_metadata")
            else (record[field] if record[field] is not None else "")
            for field in PG_COLUMNS
        ]
        writer.writerow(values)
    stream.write("\\.\n")
    stream.write(
        f"INSERT INTO poc.discovery_cache ({columns})\n"
        f"SELECT {columns} FROM _discovery_stage WHERE true\n"
        "ON CONFLICT (record_key) DO UPDATE SET\n"
        "  source_revision = EXCLUDED.source_revision,\n"
        "  display_name = EXCLUDED.display_name,\n"
        "  attributes = EXCLUDED.attributes,\n"
        "  relationships = EXCLUDED.relationships,\n"
        "  raw_metadata = EXCLUDED.raw_metadata,\n"
        "  payload_sha256 = EXCLUDED.payload_sha256,\n"
        "  last_seen_snapshot = EXCLUDED.last_seen_snapshot,\n"
        "  last_seen_at = EXCLUDED.last_seen_at;\n"
        "COMMIT;\n"
    )


def emit_surreal(snapshot: dict[str, Any], stream: TextIO) -> None:
    validate_snapshot(snapshot)
    # SurrealDB 3.x /import requires OPTION IMPORT, and commits statement by
    # statement. Stable IDs plus UPSERT make retries idempotent.
    stream.write("OPTION IMPORT;\n")
    stream.write("-- B2 discovery cache; import via /surreal import, NOT /surreal sql.\n")
    for entry in snapshot["records"]:
        record = import_record(entry, snapshot)
        stream.write(
            f"UPSERT discovery_cache:{record['record_key']} "
            f"CONTENT {canonical_json(record)} RETURN NONE;\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("pg", "surreal"), required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    try:
        # Refuse duplicate keys, corruption and invalid source payload before
        # ANY import statement is printed to stdout.
        with args.snapshot.open("r", encoding="utf-8") as handle:
            snapshot = strict_json_loads(handle.read())
        validate_snapshot(snapshot)
        import io
        buffered = io.StringIO()
        if args.engine == "pg":
            emit_pg(snapshot, buffered)
        else:
            emit_surreal(snapshot, buffered)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(error_summary("Discovery import generation", exc), file=sys.stderr)
        return 1
    sys.stdout.write(buffered.getvalue())
    print(f"Generated {args.engine} import for {len(snapshot['records'])} records", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
