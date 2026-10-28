#!/usr/bin/env python3
"""Emit PG or SurrealDB idempotent imports from ONE validated B2 snapshot.

The generator never opens a DB connection. Imports only update the separate
discovery cache. Missing entries are never deleted by an import. Generated SQL
rejects older observations and conflicting observations at the same instant.
"""

from __future__ import annotations

from metadata_primitives import error_summary, strict_json_loads

import argparse
import csv
from datetime import datetime, timezone
import io
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

# Budget for the complete transaction, measured as UTF-8 (never split/truncate).
MAX_SURREAL_IMPORT_BYTES = 512 * 1024


def observation_time(value: str) -> str:
    """Canonical comparison instant only; never rewrite a B2 snapshot/time."""
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Observation timestamp needs a timezone")
    return stamp.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def import_record(entry: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        **entry,
        "last_seen_snapshot": snapshot["snapshot_id"],
        "last_seen_at": snapshot["captured_at"],
    }


def emit_pg(snapshot: dict[str, Any], stream: TextIO) -> None:
    validate_snapshot(snapshot)
    # Validate COPY fields before emitting even BEGIN to a direct caller.
    for entry in snapshot["records"]:
        for field in ("source", "entity_type", "source_id", "source_revision", "display_name"):
            value = entry.get(field)
            if isinstance(value, str) and ("\n" in value or "\r" in value):
                raise ValueError(f"Multiline discovery field not allowed: {field}")
    stream.write("BEGIN;\n")
    stream.write("SET TRANSACTION ISOLATION LEVEL READ COMMITTED;\n")
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
        values = [
            canonical_json(record[field]) if field in ("attributes", "relationships", "raw_metadata")
            else (record[field] if record[field] is not None else "")
            for field in PG_COLUMNS
        ]
        writer.writerow(values)
    stream.write("\\.\n")
    # Serialize the state check and writes, also protecting absent keys. This
    # lock conflicts with normal DML; it does not block plain SELECT readers.
    stream.write(
        "LOCK TABLE poc.discovery_cache IN SHARE ROW EXCLUSIVE MODE;\n"
        "DO $discovery_guard$ BEGIN\n"
        "  IF EXISTS (SELECT 1 FROM poc.discovery_cache c\n"
        "    JOIN _discovery_stage s USING (record_key)\n"
        "    WHERE c.last_seen_at > s.last_seen_at\n"
        "       OR (c.last_seen_at = s.last_seen_at AND\n"
        "           to_jsonb(c) IS DISTINCT FROM to_jsonb(s))) THEN\n"
        "    RAISE EXCEPTION 'Discovery observation is stale or conflicting';\n"
        "  END IF;\n"
        "END $discovery_guard$;\n"
    )
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
    instant = canonical_json(observation_time(snapshot["captured_at"]))
    buffered = io.StringIO()
    buffered.write("OPTION IMPORT;\n")
    buffered.write("-- B2 discovery cache; import via /surreal import, NOT /surreal sql.\n")
    # THROW outside a transaction cannot protect subsequent /import writes.
    buffered.write("BEGIN TRANSACTION;\n")
    # On 3.3.4 SELECT of an absent table fails instead of returning no rows.
    # IF NOT EXISTS preserves an already-defined cache and its configuration.
    buffered.write("DEFINE TABLE IF NOT EXISTS discovery_cache SCHEMALESS;\n")
    for entry in snapshot["records"]:
        record = import_record(entry, snapshot)
        content = canonical_json({k: v for k, v in record.items() if k != "last_seen_at"})
        buffered.write(
            f"LET $current = (SELECT * FROM ONLY discovery_cache:{record['record_key']});\n"
            "IF $current != NONE {\n"
            "  LET $seen = <datetime> $current.last_seen_at;\n"
            f"  LET $payload = (SELECT * OMIT id, last_seen_at FROM ONLY discovery_cache:{record['record_key']});\n"
            f"  IF $seen > <datetime> {instant} OR ($seen = <datetime> {instant} AND $payload != {content}) {{\n"
            "    THROW 'Discovery observation is stale or conflicting';\n"
            "  };\n"
            "};\n"
            f"UPSERT discovery_cache:{record['record_key']} "
            f"CONTENT {canonical_json(record)} RETURN NONE;\n"
        )
    buffered.write("COMMIT TRANSACTION;\n")
    body = buffered.getvalue()
    if len(body.encode("utf-8")) > MAX_SURREAL_IMPORT_BYTES:
        raise ValueError("Complete guarded Surreal import exceeds UTF-8 byte budget")
    stream.write(body)


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
