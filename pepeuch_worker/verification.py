"""Pure, fail-closed verification rules. JSON reports are never authority objects."""

from copy import deepcopy
import math

from control_plane.contracts import Problem, canonical, fields, sha256
from .contracts import CPU_PROFILE


POLICY_SCHEMA = "pepeuch.worker/isolation-policy/v1"
RECEIPT_SCHEMA = "pepeuch.worker/isolation-receipt/v1"
ASSESSMENT_SCHEMA = "pepeuch.worker/isolation-assessment/v1"
CHECKS = ("identity", "groups", "privileges", "cgroup", "cpu", "memory", "swap", "pids", "code_readonly",
          "filesystem", "devices", "network_ipv4", "network_ipv6", "backend_only_port", "account_exclusive",
          "group_stop", "runtime", "backend_identity", "inherited_sockets", "unit_binding", "code_integrity")
NEGATIVE = ("secret", "sqlite", "workspace", "outside_write", "docker", "gpu", "backend_connect",
            "other_loopback", "controlled_peer", "ipv6", "child_stop", "expiration", "results_preserved")


def digest(data):
    return sha256(canonical(data).encode())


def policy(data):
    fields(data, ("schema", "profile", "configuration_sha256", "unit", "invocation_id", "cgroup", "allowed_groups",
                  "code_root", "worker_root", "backend_root", "cpu_ratio", "memory_bytes", "pids", "max_age_seconds"))
    if data["schema"] != POLICY_SCHEMA or data["profile"] != CPU_PROFILE:
        raise Problem("invalid_isolation_policy")
    import re
    from pathlib import PurePosixPath
    for name in ("configuration_sha256", "invocation_id"):
        if not isinstance(data[name], str) or re.fullmatch(r"[0-9a-f]{" + ("64" if name == "configuration_sha256" else "32") + r"}", data[name]) is None:
            raise Problem("invalid_isolation_policy")
    if not isinstance(data["unit"], str) or re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}\.service", data["unit"]) is None:
        raise Problem("invalid_isolation_policy")
    for name in ("code_root", "worker_root", "backend_root", "cgroup"):
        value = data[name]
        if (not isinstance(value, str) or not value.startswith("/") or value == "/" or ".." in PurePosixPath(value).parts
                or str(PurePosixPath(value)) != value or any(ord(c) < 33 for c in value)):
            raise Problem("invalid_isolation_policy")
    paths = [PurePosixPath(data[name]) for name in ("code_root", "worker_root", "backend_root")]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(paths) for b in paths[i + 1:]):
        raise Problem("overlapping_isolation_paths")
    if (not isinstance(data["allowed_groups"], list) or len(data["allowed_groups"]) > 16
            or any(type(g) is not int or g <= 0 for g in data["allowed_groups"]) or len(set(data["allowed_groups"])) != len(data["allowed_groups"])):
        raise Problem("invalid_isolation_policy")
    for key, high in (("memory_bytes", 134217728), ("pids", 8), ("max_age_seconds", 55)):
        if type(data[key]) is not int or not 1 <= data[key] <= high:
            raise Problem("invalid_isolation_policy")
    if type(data["cpu_ratio"]) not in (float, int) or not 0 < data["cpu_ratio"] <= 0.5:
        raise Problem("invalid_isolation_policy")
    return deepcopy(data)


def binding(observations, requested):
    process = observations["process"]
    return {"process": deepcopy(process), "profile": requested["profile"], "unit": requested["unit"],
            "invocation_id": requested["invocation_id"], "configuration_sha256": observations["configuration_sha256"],
            "policy_sha256": digest(requested)}


def receipt_errors(receipt, context, *, now, max_age):
    """Validate scope/freshness only. A valid receipt still needs trusted delivery."""
    if receipt is None:
        return ["receipt_missing"]
    try:
        fields(receipt, ("schema", "binding", "issued_monotonic", "expires_monotonic", "tests"))
        if receipt["schema"] != RECEIPT_SCHEMA or digest(receipt["binding"]) != digest(context):
            return ["receipt_binding_mismatch"]
        issued, expires = receipt["issued_monotonic"], receipt["expires_monotonic"]
        if (any(type(t) not in (int, float) or not math.isfinite(t) for t in (issued, expires, now))
                or not issued <= now < expires <= issued + max_age):
            return ["receipt_expired_or_invalid_time"]
        if not isinstance(receipt["tests"], dict) or set(receipt["tests"]) != set(NEGATIVE):
            return ["negative_tests_incomplete"]
        for name, result in receipt["tests"].items():
            fields(result, ("outcome", "method", "evidence_sha256"))
            if (result["outcome"] != "pass" or result["method"] != "independent-os-probe/v1"
                    or not isinstance(result["evidence_sha256"], str) or len(result["evidence_sha256"]) != 64
                    or any(c not in "0123456789abcdef" for c in result["evidence_sha256"])):
                return ["negative_test_not_proved:" + name]
        return []
    except (Problem, TypeError, KeyError, ValueError):
        return ["invalid_receipt"]


def assess(configuration, requested, observations, *, receipt=None, now):
    """Read-only assessment, always untrusted until an independent authority signs off.

    In particular, no field named verified, issuer_uid, or trusted in an input can
    turn this diagnostic evaluator into a launch permit.
    """
    requested = policy(requested)
    checks = {name: {"declared": True, "enforced": None, "verified": False, "reason": "independent_evidence_missing"} for name in CHECKS}
    errors = []
    try:
        status = observations["process"]["status"] or {}
        process, applied = observations["process"], observations["applied"]
        profile = configuration["os_profile"]
        def check(name, condition):
            checks[name].update(enforced=bool(condition), reason="observed_match" if condition else "observed_mismatch")
        check("identity", status.get("Uid") == [profile["expected_uid"]] * 4 and profile["expected_uid"] != 0
              and status.get("Gid") == [profile["expected_gid"]] * 4 and profile["expected_gid"] != 0
              and profile["expected_uid"] != profile["backend_uid"])
        check("groups", status.get("Groups") == sorted(requested["allowed_groups"]))
        check("privileges", status.get("NoNewPrivs") == 1 and status.get("Seccomp") == 2
              and all(status.get(key) == 0 for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")))
        check("cgroup", process.get("cgroup") == requested["cgroup"] and bool(process.get("cgroup_inode"))
              and {"cpu", "memory", "pids"} <= set(applied.get("controllers") or []))
        cpu = (applied.get("cpu.max") or "").split()
        check("cpu", len(cpu) == 2 and all(v.isdigit() for v in cpu) and int(cpu[1]) > 0
              and 0 < int(cpu[0]) / int(cpu[1]) <= requested["cpu_ratio"])
        for check_name, file, maximum in (("memory", "memory.max", requested["memory_bytes"]), ("pids", "pids.max", requested["pids"])):
            value = applied.get(file)
            check(check_name, isinstance(value, str) and value.isdigit() and 0 < int(value) <= maximum)
        check("swap", applied.get("memory.swap.max") == "0")
        unit = applied.get("systemd")
        if isinstance(unit, dict):
            check("unit_binding", unit.get("Id") == requested["unit"] and unit.get("InvocationID") == requested["invocation_id"]
                  and unit.get("MainPID") == str(process["pid"]) and unit.get("ControlGroup") == requested["cgroup"] == process["cgroup"])
        mounts = applied.get("mounts") or []
        from pathlib import PurePosixPath
        code = PurePosixPath(requested["code_root"])
        covering = [m for m in mounts if PurePosixPath(m["mountpoint"]) == code or PurePosixPath(m["mountpoint"]) in code.parents]
        if covering:
            # All deepest mount entries must be RO; stacked ambiguity is not accepted.
            deepest = max(len(m["mountpoint"]) for m in covering)
            selected = [m for m in covering if len(m["mountpoint"]) == deepest]
            check("code_readonly", len(selected) == 1 and "ro" in selected[0]["options"])
        if observations.get("stable") is not True or observations.get("unavailable"):
            errors.append("incomplete_or_unstable_observations")
        if observations.get("configuration_sha256") != digest(configuration) or requested["configuration_sha256"] != digest(configuration):
            errors.append("configuration_changed")
        errors.extend(receipt_errors(receipt, binding(observations, requested), now=now, max_age=requested["max_age_seconds"]))
    except (TypeError, ValueError, KeyError, Problem):
        errors.append("invalid_observations")
    # A caller-supplied dictionary (including a root-looking JSON) is not authority.
    errors.append("independent_authority_not_authenticated")
    return {"schema": ASSESSMENT_SCHEMA, "status": "NOT VERIFIED", "configuration_requested": deepcopy(configuration),
            "policy_requested": requested, "observations": deepcopy(observations), "negative_tests": deepcopy(receipt),
            "guarantees": checks, "errors": sorted(set(errors))}
