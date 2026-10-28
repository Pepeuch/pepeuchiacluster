"""Mandatory validators for real profiled plans, separate from query timings.

SurrealDB 3.3.4 schema characterized from an observed, sanitized response on
synthetic data. Unknown fields are retained. No conversion to legacy row plans.
"""

from copy import deepcopy
import math
import re


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Finite nonnegative execution metric required")
    return value


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("Nonnegative integer execution counter required")
    return value


def duration_ms(value):
    if not isinstance(value, str):
        raise ValueError("Explicit server duration required")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ns|µs|μs|us|ms|s)", value)
    if match is None:
        raise ValueError("Unsupported server duration")
    return number(float(match[1])*{"ns":1e-6,"µs":.001,"μs":.001,"us":.001,"ms":1,"s":1000}[match[2]])


def surreal_plan(response, *, expected_rows):
    expected_rows = integer(expected_rows)
    if (not isinstance(response, list) or len(response) != 1 or not isinstance(response[0], dict)
            or not {"result", "status", "time", "type"} <= response[0].keys() or response[0]["status"] != "OK"):
        raise ValueError("One successful 3.3.4 EXPLAIN FULL envelope required")
    envelope = response[0]
    server_ms = duration_ms(envelope["time"])
    root = envelope["result"]
    if not isinstance(root, dict) or integer(root.get("total_rows")) != expected_rows:
        raise ValueError("Executed plan row count differs from query result")
    count = 0
    def node(item, depth):
        nonlocal count
        count += 1
        if depth > 64 or count > 10000:
            raise ValueError("Plan tree complexity exceeded")
        if not isinstance(item, dict) or not {"operator", "context", "metrics"} <= item.keys():
            raise ValueError("Executed operator and metrics required")
        if any(not isinstance(item[k], str) or not item[k] or len(item[k]) > 4096 for k in ("operator", "context")):
            raise ValueError("Typed operator/context required")
        metrics = item["metrics"]
        if not isinstance(metrics, dict) or not {"elapsed_ns", "output_batches", "output_rows", "records_fetched"} <= metrics.keys():
            raise ValueError("Complete 3.3.4 operator metrics required")
        for key in ("elapsed_ns", "output_batches", "output_rows", "records_fetched"):
            integer(metrics[key])
        if "attributes" in item and not isinstance(item["attributes"], dict):
            raise ValueError("Operator attributes must be an object")
        if "expressions" in item:
            if not isinstance(item["expressions"], list) or any(not isinstance(e, dict) or not {"role", "sql"} <= e.keys()
                    or any(not isinstance(e[k], str) for k in ("role", "sql")) for e in item["expressions"]):
                raise ValueError("Typed expression descriptions required")
        children = item.get("children", [])
        if not isinstance(children, list):
            raise ValueError("Plan children must be a list")
        for child in children:
            node(child, depth+1)
    node(root, 0)
    return {"format": "pepeuch-ai.surreal-explain-334/v1", "validated": True,
            "scope": "separate_profiled_execution", "envelope_server_time_raw": envelope["time"],
            "envelope_server_time_ms": server_ms, "operator_count": count,
            "root_operator_elapsed_ns": root["metrics"]["elapsed_ns"], "total_rows": expected_rows,
            "operator_times_aggregated": False, "response": deepcopy(response)}


def postgres_plan(response, *, expected_rows):
    if not isinstance(response, list) or len(response) != 1 or not isinstance(response[0], dict):
        raise ValueError("One PostgreSQL JSON execution plan required")
    result = response[0]
    number(result.get("Planning Time"))
    number(result.get("Execution Time"))
    count = 0
    def node(item, depth):
        nonlocal count
        count += 1
        if depth > 64 or count > 10000 or not isinstance(item, dict):
            raise ValueError("Invalid or excessive PostgreSQL plan")
        if not isinstance(item.get("Node Type"), str) or not item["Node Type"]:
            raise ValueError("Typed PostgreSQL operator required")
        number(item.get("Actual Total Time"))
        integer(item.get("Actual Rows"))
        children = item.get("Plans", [])
        if not isinstance(children, list):
            raise ValueError("PostgreSQL plan children must be a list")
        for child in children:
            node(child, depth+1)
    node(result.get("Plan"), 0)
    if result["Plan"]["Actual Rows"] != integer(expected_rows):
        raise ValueError("PostgreSQL plan row count differs")
    return {"format": "pepeuch-ai.postgresql-explain/v1", "validated": True,
            "scope": "separate_profiled_execution", "planning_time_ms": result["Planning Time"],
            "execution_time_ms": result["Execution Time"], "operator_count": count,
            "operator_times_aggregated": False, "response": deepcopy(response)}
