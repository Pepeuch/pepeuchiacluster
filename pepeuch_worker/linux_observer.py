"""Bounded read-only Linux observations. No probes, secrets, subprocess or writes."""

import os
from pathlib import Path
import re
import time

from control_plane.contracts import Problem, canonical, sha256


def bounded(path, maximum=65536):
    with open(path, "rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise Problem("oversized_kernel_observation")
    return raw.decode("utf-8", errors="strict")


def process_start(raw):
    # comm may itself contain spaces and ')'; fields after the last ')' start at 3.
    if re.match(r"[1-9][0-9]* \(", raw) is None or raw.rfind(")") < raw.find("("):
        raise Problem("invalid_process_observation")
    tail = raw[raw.rfind(")") + 2:].split()
    if len(tail) < 20 or not tail[19].isdigit():
        raise Problem("invalid_process_observation")
    return int(tail[19])


def process_status(raw):
    result = {}
    required = {"Uid", "Gid", "Groups", "NoNewPrivs", "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb", "Seccomp"}
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in required:
            if key in result:
                raise Problem("duplicate_kernel_observation")
            values = value.split()
            if key in {"Uid", "Gid"}:
                if len(values) != 4:
                    raise Problem("invalid_process_observation")
                result[key] = [int(v) for v in values]
            elif key == "Groups":
                result[key] = sorted(int(v) for v in values)
            else:
                result[key] = int(value.strip(), 16 if key.startswith("Cap") else 10)
    if set(result) != required:
        raise Problem("missing_process_observation")
    return result


def cgroup_path(raw):
    lines = raw.strip().splitlines()
    if len(lines) != 1 or not lines[0].startswith("0::/"):
        raise Problem("cgroup_v2_required")
    path = lines[0][3:]
    if ".." in Path(path).parts or any(ord(char) < 32 for char in path):
        raise Problem("invalid_cgroup_observation")
    return path


def mountinfo(raw):
    result = []
    for line in raw.splitlines():
        before, separator, after = line.partition(" - ")
        left, right = before.split(), after.split()
        if not separator or len(left) < 6 or len(right) < 3:
            raise Problem("invalid_mount_observation")
        unescape = lambda value: re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)
        # Never export arbitrary mount options (which can contain sensitive data).
        flags = {"ro", "rw", "nosuid", "nodev", "noexec"}
        result.append({"root": unescape(left[3]), "mountpoint": unescape(left[4]),
                       "options": sorted(flags & set(left[5].split(","))), "type": right[0],
                       "super_options": sorted(flags & set(right[2].split(",")))})
    return result


def collect(configuration, *, pid=None, proc=Path("/proc"), cgroups=Path("/sys/fs/cgroup"), clock=time.monotonic):
    """Alternate roots are for fixtures; resulting data is never a trust grant."""
    pid = os.getpid() if pid is None else pid
    if type(pid) is not int or not 1 <= pid < 2 ** 31:
        raise Problem("invalid_process_identity")
    target = proc / str(pid)
    report = {"schema": "pepeuch.worker/linux-observations/v1", "origin": "readonly-observer",
              "observer_uid": os.geteuid(), "synthetic": proc != Path("/proc") or cgroups != Path("/sys/fs/cgroup"),
              "observed_monotonic": clock(), "configuration_sha256": sha256(canonical(configuration).encode()),
              "process": {"pid": pid}, "applied": {}, "unavailable": []}
    def observe(label, function):
        try:
            return function()
        except (OSError, ValueError, UnicodeError, Problem):
            report["unavailable"].append(label)
            return None
    start = observe("process_start", lambda: process_start(bounded(target / "stat", 4096)))
    status = observe("process_status", lambda: process_status(bounded(target / "status", 16384)))
    report["process"].update(start_ticks=start, status=status,
        boot_id=observe("boot_id", lambda: bounded(proc / "sys/kernel/random/boot_id", 128).strip()),
        kernel=observe("kernel", lambda: bounded(proc / "sys/kernel/osrelease", 256).strip()))
    report["process"]["namespaces"] = {name: observe("namespace_" + name, lambda n=name: os.readlink(target / "ns" / n))
                                              for name in ("user", "mnt", "net", "pid", "cgroup", "time")}
    group = observe("cgroup", lambda: cgroup_path(bounded(target / "cgroup", 4096)))
    report["process"]["cgroup"] = group
    report["process"]["unit_hint"] = next((part for part in reversed((group or "").split("/")) if part.endswith(".service")), None)
    def descriptors():
        result = []
        with os.scandir(target / "fd") as entries:
            for entry in entries:
                if len(result) >= 128:
                    raise Problem("too_many_process_descriptors")
                if entry.name.isdigit():
                    try:
                        destination = os.readlink(entry.path)
                    except FileNotFoundError:
                        continue
                    kind = "socket" if destination.startswith("socket:[") else "pipe" if destination.startswith("pipe:[") else "other"
                    result.append({"fd": int(entry.name), "kind": kind, "target_sha256": sha256(destination.encode())})
        return sorted(result, key=lambda item: item["fd"])
    report["applied"]["descriptor_inventory"] = observe("descriptor_inventory", descriptors)
    report["applied"]["mounts"] = observe("mounts", lambda: mountinfo(bounded(target / "mountinfo")))
    if group is not None:
        directory = cgroups / group.lstrip("/")
        report["process"]["cgroup_inode"] = observe("cgroup_inode", lambda: directory.stat().st_ino)
        report["applied"]["controllers"] = observe("controllers", lambda: bounded(cgroups / "cgroup.controllers", 4096).split())
        for name in ("cpu.max", "memory.max", "memory.swap.max", "pids.max"):
            report["applied"][name] = observe(name, lambda n=name: bounded(directory / n, 256).strip())
    # Detect PID recycling, termination and changes during the measurement itself.
    end = observe("process_start_after", lambda: process_start(bounded(target / "stat", 4096)))
    report["stable"] = start is not None and start == end
    if group is not None:
        after = observe("cgroup_after", lambda: cgroup_path(bounded(target / "cgroup", 4096)))
        report["stable"] = report["stable"] and after == group
    return report
