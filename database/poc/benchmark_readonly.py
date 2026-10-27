#!/usr/bin/env python3
"""Read-only PostgreSQL/SurrealDB query parity probe for the 405-model POC.

Uses existing internal Docker Compose networks. Milliseconds include Docker
exec and CLI startup: these are NOT engine execution-time benchmarks.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PG_COMPOSE = "infrastructure/docker/compose.db-poc.yaml"
SURREAL_COMPOSE = "infrastructure/docker/compose.surreal-poc.yaml"
SHA = "5e9fdbc3d88cb831627a93dc1362cc10773c176c"


@dataclass(frozen=True)
class Query:
    name: str
    pg: str
    surreal: str
    kind: str = "count"
    expected: int | None = None


def count_query(name: str, pg_where: str, surreal_where: str, expected: int | None = None) -> Query:
    return Query(
        name,
        f"SELECT count(*) FROM poc.external_models WHERE source_commit = '{SHA}'{pg_where};",
        f"SELECT count() AS n FROM external_models WHERE source_commit = '{SHA}'{surreal_where} GROUP ALL;",
        expected=expected,
    )


CASES = (
    count_query("total", "", "", 405),
    count_query("open_weights", " AND open_weights IS TRUE", " AND open_weights = true", 196),
    count_query("positive_context", " AND context_tokens > 0", " AND context_tokens > 0", 397),
    count_query("zero_context", " AND context_tokens = 0", " AND context_tokens = 0", 8),
    count_query("with_weights", " AND weights_count > 0", " AND weights_count > 0", 154),
    count_query("with_benchmarks", " AND benchmarks_count > 0", " AND benchmarks_count > 0", 135),
    count_query("tools_supported", " AND tools_supported IS TRUE", " AND tools_supported = true"),
    count_query(
        "gpt41_tools_regression",
        " AND model_id = 'openai/gpt-4.1' AND tools_supported IS TRUE",
        " AND model_id = 'openai/gpt-4.1' AND tools_supported = true",
        1,
    ),
    count_query(
        "gpt41_raw_tool_call",
        " AND model_id = 'openai/gpt-4.1' AND raw_metadata->>'tool_call' = 'true'",
        " AND model_id = 'openai/gpt-4.1' AND raw_metadata.tool_call = true",
        1,
    ),
    count_query("family_qwen", " AND family = 'qwen'", " AND family = 'qwen'"),
    count_query("combined_filter", " AND open_weights IS TRUE AND context_tokens >= 65536", " AND open_weights = true AND context_tokens >= 65536"),
    count_query("nested_name", " AND raw_metadata->>'name' = 'Jamba Large'", " AND raw_metadata.name = 'Jamba Large'"),
    Query(
        "exact_model",
        f"SELECT model_id FROM poc.external_models WHERE source_commit = '{SHA}' AND model_id = 'ai21/jamba-large' ORDER BY model_id;",
        f"SELECT VALUE model_id FROM external_models WHERE source_commit = '{SHA}' AND model_id = 'ai21/jamba-large' ORDER BY model_id;",
        kind="ids",
    ),
    Query(
        "first_five_models",
        f"SELECT model_id FROM poc.external_models WHERE source_commit = '{SHA}' ORDER BY model_id LIMIT 5;",
        f"SELECT VALUE model_id FROM external_models WHERE source_commit = '{SHA}' ORDER BY model_id LIMIT 5;",
        kind="ids",
    ),
)


class ProbeError(RuntimeError):
    pass


def normalize_pg(output: str, kind: str) -> int | list[str]:
    lines = output.strip().splitlines() if output.strip() else []
    if kind == "ids":
        return lines
    if kind != "count" or len(lines) != 1:
        raise ProbeError(f"Unexpected PostgreSQL output: {lines!r}")
    try:
        return int(lines[0])
    except ValueError as exc:
        raise ProbeError(f"Non-integer PostgreSQL count: {lines[0]!r}") from exc


def normalize_surreal(output: str, kind: str) -> int | list[str]:
    try:
        value: Any = json.loads(output.strip())
    except json.JSONDecodeError as exc:
        raise ProbeError(f"Cannot decode SurrealDB JSON output: {exc}") from exc
    while isinstance(value, dict) and "result" in value:
        value = value["result"]
    while isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list):
        raise ProbeError(f"Unexpected SurrealDB output: {value!r}")
    if kind == "ids":
        if not all(isinstance(item, str) for item in value):
            raise ProbeError(f"Expected string model IDs: {value!r}")
        return value
    if kind != "count" or len(value) != 1 or not isinstance(value[0], dict):
        raise ProbeError(f"Expected one SurrealDB aggregate: {value!r}")
    result = value[0].get("n")
    if isinstance(result, bool) or not isinstance(result, int):
        raise ProbeError(f"Expected integer SurrealDB count: {result!r}")
    return result


def run_cli(command: list[str], sql: str, timeout: int) -> tuple[str, float]:
    start = perf_counter()
    try:
        completed = subprocess.run(
            command, input=sql + "\n", text=True, capture_output=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(f"CLI could not run: {exc}") from exc
    elapsed = (perf_counter() - start) * 1000
    if completed.returncode != 0:
        raise ProbeError(
            f"CLI exit {completed.returncode}: {completed.stderr.strip()[:400]}"
        )
    return completed.stdout, round(elapsed, 2)


def probe(timeout: int) -> list[dict[str, Any]]:
    pg_cmd = [
        "docker", "compose", "-f", PG_COMPOSE, "exec", "-T", "postgres",
        "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
        "-U", "pepeuch_ai", "-d", "pepeuch_ai",
    ]
    surreal_cmd = [
        "docker", "compose", "-f", SURREAL_COMPOSE, "exec", "-T", "surrealdb",
        "/surreal", "sql", "--endpoint", "http://127.0.0.1:8000",
        "--namespace", "pepeuch_ai", "--database", "poc",
        "--hide-welcome", "--json", "--log", "none",
    ]
    rows = []
    for position, query in enumerate(CASES, 1):
        pg_out, pg_ms = run_cli(pg_cmd + ["-c", query.pg], "", timeout)
        surreal_out, surreal_ms = run_cli(surreal_cmd, query.surreal, timeout)
        pg = normalize_pg(pg_out, query.kind)
        surreal = normalize_surreal(surreal_out, query.kind)
        same = pg == surreal and (query.expected is None or pg == query.expected)
        rows.append({
            "case": query.name, "match": same, "postgres": pg,
            "surrealdb": surreal,
            "postgres_cli_ms": pg_ms, "surrealdb_cli_ms": surreal_ms,
        })
        print(
            f"[{position:02}/{len(CASES):02}] {query.name}: "
            f"{'OK' if same else 'DIFFERENT'}; PG={pg!r} Surreal={surreal!r}",
            file=sys.stderr,
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--json-report", type=Path, default=None)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    if not all((ROOT / f).is_file() for f in (PG_COMPOSE, SURREAL_COMPOSE)):
        parser.error("Expected both POC Compose files in the current repository")
    try:
        data = probe(args.timeout)
    except ProbeError as exc:
        print(f"Probe stopped: {exc}", file=sys.stderr)
        return 2
    passed = sum(row["match"] for row in data)
    print(f"Read-only query parity: {passed}/{len(data)}")
    print("CLI times include Docker exec and client startup: NOT engine latency.")
    if args.json_report is not None:
        if args.json_report.exists():
            print("Refusing to overwrite an existing report", file=sys.stderr)
            return 2
        args.json_report.write_text(
            json.dumps({"snapshot": SHA, "checks": data}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Report: {args.json_report}")
    return 0 if passed == len(data) else 1


if __name__ == "__main__":
    raise SystemExit(main())
