#!/usr/bin/env python3
"""Compare two offline B2 snapshots, without guessing deletions or writing DBs."""

from __future__ import annotations

from metadata_primitives import error_summary, strict_json_loads

import argparse
import json
from pathlib import Path
import sys

from discovery_cache import compare_snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    try:
        with args.before.open("r", encoding="utf-8") as handle:
            old = strict_json_loads(handle.read())
        with args.after.open("r", encoding="utf-8") as handle:
            new = strict_json_loads(handle.read())
        result = compare_snapshots(old, new)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(error_summary("Discovery comparison", exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
