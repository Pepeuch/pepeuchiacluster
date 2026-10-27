#!/usr/bin/env python3
"""B3.3: bounded anonymous MoArk roster GET, one B2 inference_endpoint.

No tokens, inference requests, weights, database imports or automatic retries.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from discovery_cache import make_snapshot, validate_snapshot
from moark_adapter import API_BASE, CATALOG_URL, model_id, select_moark_model


DEFAULT_MODEL = "Qwen3-8B"
MAX_METADATA_BYTES = 2_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_online(requested_id: str) -> dict:
    model_id(requested_id)  # Reject invalid selections before any network I/O.
    request = Request(CATALOG_URL, headers={
        "Accept": "application/json", "User-Agent": "Pepeuch-AI-Discovery-POC/0.1",
    }, method="GET")
    with build_opener(_NoRedirect()).open(request, timeout=20) as response:
        payload = response.read(MAX_METADATA_BYTES + 1)
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError("MoArk metadata response exceeded size limit")
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("MoArk roster must be an object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", type=Path, help="Read a synthetic roster; never import as real data")
    mode.add_argument("--online", action="store_true", help="One anonymous GET of the official public roster")
    parser.add_argument("--model-id", default=DEFAULT_MODEL)
    args = parser.parse_args()
    try:
        model_id(args.model_id)
        data = read_online(args.model_id) if args.online else json.loads(args.fixture.read_text(encoding="utf-8"))
        record = select_moark_model(data, requested_id=args.model_id)
        snapshot = make_snapshot([record], scope={"moark": {
            "mode": "exact_ids", "ids": [args.model_id], "endpoint": API_BASE,
            "catalog_url": CATALOG_URL, "authentication": "anonymous",
            "input": "public_api" if args.online else "synthetic_fixture",
        }})
        validate_snapshot(snapshot)
    except HTTPError as exc:
        print(f"MoArk metadata probe failed (HTTP {exc.code}); no snapshot written", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        # Do not echo third-party response bodies, tokens, URLs or field values.
        print(f"MoArk metadata probe failed ({type(exc).__name__}); no snapshot written", file=sys.stderr)
        return 1
    print(f"Prepared 1 MoArk inference endpoint; snapshot {snapshot['snapshot_id']}", file=sys.stderr)
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
