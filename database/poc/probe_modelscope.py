#!/usr/bin/env python3
"""Read a single ModelScope model's repository metadata into a B3.1 snapshot.

Offline fixture by default unless --online is explicit. Online mode requires
the official `modelscope-hub` SDK; it uses only HubApi.get_repo(), never model
downloads, token login, database ingestion, upload, or deployment.
"""

from __future__ import annotations

from metadata_primitives import error_summary, strict_json_loads

import argparse
import json
from pathlib import Path
import sys

from discovery_cache import make_snapshot
from modelscope_adapter import normalize_modelscope_repo


DEFAULT_ID = "Qwen/Qwen3-0.6B"
ENDPOINTS = ("https://modelscope.cn", "https://modelscope.ai")


def read_online(model_id: str, endpoint: str) -> dict:
    # Do not import the SDK for offline contract tests or read-only fixtures.
    from modelscope_hub import HubApi

    info = HubApi(endpoint=endpoint).get_repo(model_id, repo_type="model")
    # Official RepoInfo.to_dict preserves source metadata. We do not request
    # file listings or a mutable 'revision' (get_repo ignores that argument).
    result = info.to_dict()
    if not isinstance(result, dict):
        raise ValueError("ModelScope SDK returned an invalid RepoInfo payload")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", type=Path, help="Load a local RepoInfo.to_dict fixture")
    mode.add_argument("--online", action="store_true", help="Get public repository metadata via official SDK")
    parser.add_argument("--model-id", default=DEFAULT_ID)
    parser.add_argument("--endpoint", choices=ENDPOINTS, default=ENDPOINTS[0])
    args = parser.parse_args()

    if args.online:
        try:
            data = read_online(args.model_id, args.endpoint)
        except ModuleNotFoundError:
            print("Official modelscope-hub SDK unavailable; use an isolated venv or --fixture", file=sys.stderr)
            return 2
        except Exception as exc:
            # Avoid echoing third-party API error bodies or any configured token.
            print(error_summary("ModelScope", exc), file=sys.stderr)
            return 1
    else:
        try:
            data = strict_json_loads(args.fixture.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            print(error_summary("ModelScope fixture", exc), file=sys.stderr)
            return 1

    try:
        record = normalize_modelscope_repo(data, requested_id=args.model_id)
        snapshot = make_snapshot(
            [record], scope={"modelscope": {
                "mode": "exact_ids", "ids": [args.model_id],
                "endpoint": args.endpoint,
            }},
        )
    except (TypeError, ValueError) as exc:
        print(error_summary("ModelScope", exc), file=sys.stderr)
        return 1
    print(f"Prepared 1 ModelScope record; snapshot {snapshot['snapshot_id']}", file=sys.stderr)
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
