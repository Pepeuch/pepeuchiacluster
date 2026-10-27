#!/usr/bin/env python3
"""B3.2 bounded read-only CSGHub model metadata probe (no SDK download)."""

from __future__ import annotations

from metadata_primitives import error_summary, strict_json_loads

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import build_opener

from csghub_adapter import model_id, normalize_csghub_model
from discovery_cache import make_snapshot
from metadata_http import HTTPPolicy, NoRedirect as _NoRedirect, UrllibTransport, get_metadata_json


DEFAULT_MODEL = "OpenCSG/csg-wukong-1B"
OFFICIAL_ENDPOINT = "https://hub.opencsg.com"
MAX_METADATA_BYTES = 2_000_000


def read_online(requested_id: str) -> dict:
    """Follow the SDK's get_repo_meta_path for source='csg', revision='main'."""
    namespace, name = model_id(requested_id).split("/")
    path = "/".join(quote(part, safe="") for part in (namespace, name))
    url = f"{OFFICIAL_ENDPOINT}/csg/api/models/{path}/revision/main"
    # No auth, cookies, redirects, POST or model downloads.
    return get_metadata_json(url, policy=HTTPPolicy(
        frozenset({"hub.opencsg.com"}), MAX_METADATA_BYTES, 20,
    ), transport=UrllibTransport(build_opener(_NoRedirect())))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", type=Path, help="Read a synthetic model-info JSON fixture")
    mode.add_argument("--online", action="store_true", help="GET public official repository metadata")
    parser.add_argument("--model-id", default=DEFAULT_MODEL)
    args = parser.parse_args()
    try:
        model_id(args.model_id)
        if args.online:
            data = read_online(args.model_id)
        else:
            data = strict_json_loads(args.fixture.read_text(encoding="utf-8"))
        record = normalize_csghub_model(data, requested_id=args.model_id)
        snapshot = make_snapshot([record], scope={
            "csghub": {
                "mode": "exact_ids", "ids": [args.model_id],
                "endpoint": OFFICIAL_ENDPOINT, "source": "csg", "revision_request": "main",
            },
        })
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        # Never print API error bodies or credentials to logs.
        print(error_summary("CSGHub", exc), file=sys.stderr)
        return 1
    print(f"Prepared 1 CSGHub model record; snapshot {snapshot['snapshot_id']}", file=sys.stderr)
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
