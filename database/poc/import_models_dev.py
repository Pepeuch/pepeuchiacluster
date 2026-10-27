#!/usr/bin/env python3
"""Stream a pinned models.dev TOML snapshot into PostgreSQL using COPY.

Only Python's standard library is required. The resulting SQL/COPY stream goes
to stdout; diagnostics go to stderr. Run it through psql with ON_ERROR_STOP=1
and a shell with pipefail enabled, as described in database/poc/README.md.

This POC intentionally retains the raw TOML metadata as JSONB. It does not
claim to define the final normalized Personal Model Catalog schema.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any, TextIO


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "external" / "models.dev"
SOURCE_NAME = "models.dev"
COPY_COLUMNS = (
    "source", "source_commit", "source_path", "model_id", "display_name",
    "family", "open_weights", "context_tokens", "tools_supported",
    "weights_count", "benchmarks_count", "raw_metadata",
)


def _git(source_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def source_commit(source_root: Path) -> str:
    sha = _git(source_root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError(f"Invalid source SHA: {sha!r}")
    if _git(source_root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("models.dev has local changes; refusing non-reproducible import")
    return sha


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise TypeError(f"Cannot JSON-encode {type(value).__name__}")


def _supported_tools(model: dict[str, Any]) -> bool | None:
    caps = model.get("capabilities")
    if not isinstance(caps, dict):
        return None
    tools = caps.get("tools")
    if not isinstance(tools, dict):
        return None
    value = tools.get("supported")
    return value if isinstance(value, bool) else None


def _bool_csv(value: Any) -> str:
    if not isinstance(value, bool):
        return ""
    return "true" if value else "false"


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def make_row(source_root: Path, path: Path, commit: str) -> list[Any]:
    models_dir = source_root / "models"
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked model file: {path}")
    rel = path.relative_to(models_dir)
    with path.open("rb") as handle:
        model = tomllib.load(handle)

    family = model.get("family")
    display_name = str(model.get("name") or path.stem)
    family_name = family if isinstance(family, str) else ""
    source_path = (Path("models") / rel).as_posix()
    # A literal newline in a CSV field could create a standalone COPY `\\.` line.
    # Reject such files rather than letting external metadata alter SQL framing.
    for field in (source_path, display_name, family_name):
        if "\n" in field or "\r" in field:
            raise ValueError(f"Multiline field not supported in {path}")
    limits = model.get("limit")
    context = limits.get("context") if isinstance(limits, dict) else None
    if isinstance(context, bool) or not isinstance(context, int) or context < 0:
        context = None

    metadata = json.dumps(
        model,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return [
        SOURCE_NAME,
        commit,
        source_path,
        rel.with_suffix("").as_posix(),
        display_name,
        family_name,
        _bool_csv(model.get("open_weights")),
        context if context is not None else "",
        _bool_csv(_supported_tools(model)),
        _count(model.get("weights")),
        _count(model.get("benchmarks")),
        metadata,
    ]


def emit_copy(rows: list[list[Any]], output: TextIO) -> None:
    # All imported values are CSV data, never interpolated into SQL statements.
    output.write("BEGIN;\n")
    output.write(
        "CREATE TEMP TABLE _models_dev_stage "
        "(LIKE poc.external_models INCLUDING DEFAULTS) ON COMMIT DROP;\n"
    )
    columns = ", ".join(COPY_COLUMNS)
    output.write(
        f"COPY _models_dev_stage ({columns}) "
        "FROM STDIN WITH (FORMAT csv, HEADER true);\n"
    )
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(COPY_COLUMNS)
    writer.writerows(rows)
    output.write("\\.\n")
    output.write(
        f"INSERT INTO poc.external_models ({columns})\n"
        f"SELECT {columns} FROM _models_dev_stage WHERE true\n"
        "ON CONFLICT (source, source_commit, source_path) DO UPDATE SET\n"
        "    model_id = EXCLUDED.model_id,\n"
        "    display_name = EXCLUDED.display_name,\n"
        "    family = EXCLUDED.family,\n"
        "    open_weights = EXCLUDED.open_weights,\n"
        "    context_tokens = EXCLUDED.context_tokens,\n"
        "    tools_supported = EXCLUDED.tools_supported,\n"
        "    weights_count = EXCLUDED.weights_count,\n"
        "    benchmarks_count = EXCLUDED.benchmarks_count,\n"
        "    raw_metadata = EXCLUDED.raw_metadata,\n"
        "    imported_at = now();\n"
        "COMMIT;\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=DEFAULT_SOURCE_ROOT,
        help="Checked-out models.dev git submodule",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Import the first N sorted TOML files (default: all)",
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
            paths = paths[: args.limit]
        if not paths:
            raise ValueError("No TOML models found")
        rows = [make_row(root, path, commit) for path in paths]
    except (OSError, ValueError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as exc:
        print(f"Import preparation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Prepared {len(rows)} model records from {commit}", file=sys.stderr)
    emit_copy(rows, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
