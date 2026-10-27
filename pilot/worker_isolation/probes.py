"""Fixed probes only. Importing this module performs no I/O or networking."""

import errno
import ipaddress
import os
from pathlib import Path
import socket
import stat

from control_plane.contracts import Problem, fields


SCHEMA = "pepeuch.worker/isolation-pilot/v1"
CASES = ("secret", "sqlite", "workspace", "outside_write", "docker", "gpu", "backend_connect", "other_loopback",
         "controlled_peer", "ipv6", "resources", "child_stop", "expiration", "results_preserved")
FILES = {"secret": "backend/secrets/admin.canary", "sqlite": "backend/app/index.canary", "workspace": "backend/workspaces/forbidden.canary",
         "outside_write": "host-write.canary", "results_preserved": "published/result.canary"}


def scope(data):
    import re
    fields(data, ("schema", "run_id", "fixture_root", "backend_port", "blocked_loopback_port", "peer_ipv4", "peer_ipv6",
                  "peer_port", "expected_uid", "expected_gid", "boot_id", "created_monotonic", "expires_monotonic"))
    if data["schema"] != SCHEMA or not isinstance(data["run_id"], str) or re.fullmatch(r"[0-9a-f]{32}", data["run_id"]) is None:
        raise Problem("invalid_pilot_scope")
    expected = "pepeuch-b531-fixtures-" + data["run_id"]
    if data["fixture_root"] not in ("/opt/" + expected, "/var/lib/" + expected):
        raise Problem("synthetic_fixture_scope_required")
    for name in ("backend_port", "blocked_loopback_port", "peer_port"):
        if type(data[name]) is not int or not 1024 <= data[name] <= 65535:
            raise Problem("invalid_pilot_scope")
    if data["backend_port"] == data["blocked_loopback_port"]:
        raise Problem("separate_control_port_required")
    for name in ("expected_uid", "expected_gid"):
        if type(data[name]) is not int or not 1 <= data[name] < 2 ** 31:
            raise Problem("nonroot_dedicated_identity_required")
    try:
        v4, v6 = ipaddress.ip_address(data["peer_ipv4"]), ipaddress.ip_address(data["peer_ipv6"])
        if not any(v4 in ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")) or v6 not in ipaddress.ip_network("fc00::/7"):
            raise ValueError()
    except (ValueError, TypeError):
        raise Problem("controlled_private_peers_only") from None
    import math
    created, expires = data["created_monotonic"], data["expires_monotonic"]
    if (any(type(t) not in (int, float) or not math.isfinite(t) for t in (created, expires))
            or not 0 <= created < expires <= created + 600 or not isinstance(data["boot_id"], str)
            or re.fullmatch(r"[0-9a-f-]{36}", data["boot_id"]) is None):
        raise Problem("invalid_pilot_scope")
    return dict(data)


def deny_open(path, *, writing=False):
    """Never read bytes or write/truncate, even if the supposed denial fails."""
    flags = (os.O_WRONLY if writing else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        from pepeuch_worker.private_io import opened_directory
        path = Path(path)
        with opened_directory(path.parent) as parent:
            fd = os.open(path.name, flags, dir_fd=parent)
        os.close(fd)
        return {"outcome": "FAIL", "detail": "unexpected_access", "errno": None}
    except OSError as exc:
        denied = exc.errno in ((errno.EACCES, errno.EPERM, errno.EROFS) if writing else (errno.EACCES, errno.EPERM))
        return {"outcome": "candidate_denial" if denied else "NOT VERIFIED", "detail": "open_errno", "errno": exc.errno}
    except Problem:
        return {"outcome": "NOT VERIFIED", "detail": "unsafe_or_changed_fixture", "errno": None}


def connect(scope_data, case):
    if case == "backend_connect":
        family, host, port = socket.AF_INET, "127.0.0.1", scope_data["backend_port"]
    elif case == "other_loopback":
        family, host, port = socket.AF_INET, "127.0.0.1", scope_data["blocked_loopback_port"]
    elif case == "controlled_peer":
        family, host, port = socket.AF_INET, scope_data["peer_ipv4"], scope_data["peer_port"]
    elif case == "ipv6":
        family, host, port = socket.AF_INET6, scope_data["peer_ipv6"], scope_data["peer_port"]
    else:
        raise Problem("unknown_fixed_probe")
    try:
        with socket.socket(family, socket.SOCK_STREAM) as client:
            client.settimeout(0.3)
            client.connect((host, port))  # No request, credential or byte is sent.
        return {"outcome": "candidate_reachable" if case == "backend_connect" else "FAIL", "detail": "connected", "errno": None}
    except OSError as exc:
        denied = exc.errno in (errno.EACCES, errno.EPERM) and case != "backend_connect"
        return {"outcome": "candidate_denial" if denied else "NOT VERIFIED", "detail": "connect_errno", "errno": exc.errno}


def device_metadata():
    # Never open GPU nodes or connect to an actual Docker socket.
    paths = ("/run/docker.sock", "/var/run/docker.sock", "/dev/dri", "/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm")
    result = {}
    for path in paths:
        try:
            info = os.lstat(path)
            result[path] = "visible_socket" if stat.S_ISSOCK(info.st_mode) else "visible"
        except OSError as exc:
            result[path] = {"errno": exc.errno}
    return {"outcome": "NOT VERIFIED", "detail": "metadata_requires_external_host_inventory", "devices": result}


def require_lifecycle_limits(observed):
    """No child/wait pilot until the actual process/cgroup has bounded limits."""
    try:
        status, limits = observed["process"]["status"], observed["applied"]
        cpu = limits["cpu.max"].split()
        valid = (observed["stable"] is True and not observed["unavailable"] and observed["process"]["cgroup"] != "/"
                 and status["Uid"][1] != 0 and status["NoNewPrivs"] == 1
                 and all(status[name] == 0 for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
                 and len(cpu) == 2 and 0 < int(cpu[0]) / int(cpu[1]) <= 0.5
                 and 0 < int(limits["memory.max"]) <= 134217728 and limits["memory.swap.max"] == "0"
                 and 0 < int(limits["pids.max"]) <= 8)
    except (TypeError, KeyError, ValueError, ZeroDivisionError):
        valid = False
    if not valid:
        raise Problem("lifecycle_probe_limits_not_verified")
