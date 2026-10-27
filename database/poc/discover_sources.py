#!/usr/bin/env python3
"""Manual multi-source discovery using synthetic local fixtures only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from discovery_registry import DEFAULT_MANIFEST, FIXTURE_BINDINGS, discover_fixtures
from metadata_primitives import error_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixtures", action="store_true", help="Normalize local synthetic fixtures; never import as real observations")
    mode.add_argument("--list-sources", action="store_true", help="List source descriptions without loading fixtures or adapters")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source", action="append", choices=tuple(FIXTURE_BINDINGS), help="Repeat to select sources; default: all seven")
    parser.add_argument("--captured-at", help="Override the fixture manifest's fixed observation timestamp")
    args = parser.parse_args()
    if args.list_sources:
        if args.source is not None or args.captured_at is not None:
            parser.error("--source and --captured-at require --fixtures")
        print(json.dumps([{
            "source": name, "entity_types": sorted(binding.spec.entity_types),
            "selection_modes": sorted(binding.spec.selection_modes),
        } for name, binding in FIXTURE_BINDINGS.items()], sort_keys=True))
        return 0
    try:
        snapshot = discover_fixtures(args.manifest, sources=args.source, captured_at=args.captured_at)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(error_summary("Fixture discovery", exc), file=sys.stderr)
        return 1
    print(f"Prepared {len(snapshot['records'])} SYNTHETIC fixture records; do not import as real observations", file=sys.stderr)
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
