"""Synthetic verification data. Never a receipt usable by the strict runtime."""

from copy import deepcopy
import json
from pathlib import Path

from pepeuch_worker.verification import NEGATIVE, POLICY_SCHEMA, RECEIPT_SCHEMA, binding, digest


def configuration():
    data = json.loads(Path("deploy/worker-linux/worker-config.example.json").read_text())
    data["os_profile"].update(expected_uid=1001, expected_gid=1001, backend_uid=1000)
    return data


def requested(config=None):
    config = configuration() if config is None else config
    return {"schema": POLICY_SCHEMA, "profile": config["os_profile"]["schema"], "configuration_sha256": digest(config),
            "unit": "pepeuch-test.service", "invocation_id": "a" * 32, "cgroup": "/system.slice/pepeuch-test.service",
            "allowed_groups": [1001], "code_root": "/opt/pepeuch-test-code", "worker_root": "/var/lib/pepeuch-test-worker",
            "backend_root": "/var/lib/pepeuch-test-backend", "cpu_ratio": 0.5, "memory_bytes": 134217728,
            "pids": 8, "max_age_seconds": 30}


def observations(config=None):
    config = configuration() if config is None else config
    return {"schema": "pepeuch.worker/linux-observations/v1", "synthetic": True, "origin": "readonly-observer",
            "observer_uid": 1001, "observed_monotonic": 100, "configuration_sha256": digest(config), "unavailable": [], "stable": True,
            "process": {"pid": 42, "start_ticks": 1234, "boot_id": "synthetic-boot", "kernel": "synthetic-kernel",
                "namespaces": {name: name + ":[42]" for name in ("user", "mnt", "net", "pid", "cgroup")},
                "cgroup": "/system.slice/pepeuch-test.service", "cgroup_inode": 77,
                "status": {"Uid": [1001] * 4, "Gid": [1001] * 4, "Groups": [1001], "NoNewPrivs": 1,
                    "CapInh": 0, "CapPrm": 0, "CapEff": 0, "CapBnd": 0, "CapAmb": 0, "Seccomp": 2}},
            "applied": {"controllers": ["cpu", "memory", "pids"], "cpu.max": "50000 100000", "memory.max": "134217728",
                "memory.swap.max": "0", "pids.max": "8", "mounts": [{"root": "/", "mountpoint": "/", "options": ["ro"], "type": "ext4", "super_options": ["rw"]}]}}


def receipt(obs=None, config=None, requirement=None):
    config = configuration() if config is None else config
    obs = observations(config) if obs is None else obs
    requirement = requested(config) if requirement is None else requirement
    return {"schema": RECEIPT_SCHEMA, "binding": binding(obs, requirement), "issued_monotonic": 100,
            "expires_monotonic": 120, "tests": {name: {"outcome": "pass", "method": "independent-os-probe/v1", "evidence_sha256": "b" * 64} for name in NEGATIVE}}
