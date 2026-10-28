#!/usr/bin/env python3
"""Engine-neutral SYNTHETIC comparison corpus and acceptance gate, no DB access.

The reference results are literal fixtures, not timings or a database verdict.
This does not execute SQL, import data, provision services or choose an engine.
"""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "fixtures/comparison.synthetic.json"


def load_workload(path=CORPUS):
    raw = Path(path).read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError("Bounded synthetic corpus required")
    from metadata_primitives import strict_json_loads
    data = strict_json_loads(raw)
    if (not isinstance(data, dict) or data.get("format") != "pepeuch-ai.db-comparison-corpus/v1"
            or data.get("data_kind") != "synthetic"):
        raise ValueError("Explicit synthetic comparison corpus required")
    return data, hashlib.sha256(raw).hexdigest()


def validate_measurement(report, *, corpus=None):
    """Accept separately measured reports only; reject process-launch benchmarks.

    Structural validation cannot establish authenticity of operator measurements.
    Engine results must be normalized and rounded as specified in the protocol.
    """
    data, fingerprint = load_workload() if corpus is None else corpus
    if not isinstance(report, dict) or set(report) != {
        "format", "engine", "version", "image_digest", "corpus_sha256", "timing_scope",
        "resources", "indexes", "queries", "import_update", "backup_restore"
    }:
        raise ValueError("Complete measured report required")
    if (report["format"] != "pepeuch-ai.db-comparison-measurement/v1"
            or report["engine"] not in {"postgresql", "surrealdb"}
            or report["corpus_sha256"] != fingerprint
            or report["timing_scope"] not in {"engine", "persistent_client"}
            or not isinstance(report["version"], str) or not report["version"]
            or not isinstance(report["image_digest"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", report["image_digest"])):
        raise ValueError("Comparable engine identity, corpus and timing scope required")
    def number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Finite nonnegative metric required")
        return value
    resources = report["resources"]
    if not isinstance(resources, dict) or set(resources) != {"cpu_limit", "memory_limit_bytes", "peak_rss_bytes", "cpu_seconds"}:
        raise ValueError("CPU/RAM limits and observations required")
    for metric in resources.values():
        number(metric)
    if resources["cpu_limit"] <= 0 or resources["memory_limit_bytes"] <= 0:
        raise ValueError("Explicit positive limits required")
    if resources["peak_rss_bytes"] > resources["memory_limit_bytes"]:
        raise ValueError("Inconsistent memory measurement")
    if not isinstance(report["indexes"], list) or any(not isinstance(i, str) or not i for i in report["indexes"]):
        raise ValueError("Explicit index descriptions required")
    queries = report["queries"]
    if not isinstance(queries, dict) or set(queries) != set(data["expected"]):
        raise ValueError("Every representative query required")
    for name, expected in data["expected"].items():
        measured = queries[name]
        if not isinstance(measured, dict) or set(measured) != {"result", "samples_ms", "plan", "cache_state"}:
            raise ValueError("Results, raw samples and plans required")
        if json.dumps(measured["result"], sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Query parity failed")
        samples = measured["samples_ms"]
        if not isinstance(samples, list) or not 10 <= len(samples) <= 10_000:
            raise ValueError("Bounded repeatable timing samples required")
        for sample in samples:
            number(sample)
        if not isinstance(measured["plan"], str) or not measured["plan"] or measured["cache_state"] not in {"cold", "warm"}:
            raise ValueError("Explicit cache state and query plan required")
    for name in ("import_update", "backup_restore"):
        observation = report[name]
        if not isinstance(observation, dict) or set(observation) != {"verified", "evidence"}:
            raise ValueError("Explicit import and restore evidence required")
        if observation["verified"] is not True or not isinstance(observation["evidence"], str) or not observation["evidence"]:
            raise ValueError("Unverified engine operation")
    return report


def comparison(left, right):
    a, b = validate_measurement(left), validate_measurement(right)
    if (a["engine"] == b["engine"] or a["timing_scope"] != b["timing_scope"]
            or a["resources"]["cpu_limit"] != b["resources"]["cpu_limit"]
            or a["resources"]["memory_limit_bytes"] != b["resources"]["memory_limit_bytes"]
            or any(a["queries"][q]["cache_state"] != b["queries"][q]["cache_state"] for q in a["queries"])):
        raise ValueError("Matched engine profiles required")
    def percentile(samples, fraction):
        return sorted(samples)[max(0, math.ceil(len(samples) * fraction) - 1)]
    return {"format": "pepeuch-ai.db-comparison-summary/v1", "data_kind": "synthetic",
            "measurement_origin": "operator_supplied_not_attested", "corpus_sha256": a["corpus_sha256"],
            "decision": "requires_review", "engines": {
                r["engine"]: {q: {"p50_ms": percentile(v["samples_ms"], .5), "p95_ms": percentile(v["samples_ms"], .95)}
                              for q, v in r["queries"].items()} for r in (a, b)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-report", type=Path)
    parser.add_argument("--surreal-report", type=Path)
    args = parser.parse_args()
    if not args.postgres_report and not args.surreal_report:
        corpus, fingerprint = load_workload()
        print(json.dumps({"status": "BLOCKED", "reason": "isolated_measurements_require_go",
                          "data_kind": "synthetic", "corpus_sha256": fingerprint, "workload": corpus}, sort_keys=True))
        return 0
    if not args.postgres_report or not args.surreal_report:
        parser.error("Both independently measured engine reports are required")
    from metadata_primitives import strict_json_loads
    try:
        reports = []
        for path in (args.postgres_report, args.surreal_report):
            with path.open("rb") as stream:
                raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Bounded report required")
            reports.append(strict_json_loads(raw))
        if reports[0].get("engine") != "postgresql" or reports[1].get("engine") != "surrealdb":
            raise ValueError("Report engine mismatch")
        result = comparison(*reports)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        parser.exit(2, "Comparison refused: incomplete, incompatible or invalid measurements\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
