"""Read-only observations. No setting, self-report or unit file proves isolation."""

import os
from pathlib import Path

from .contracts import EVIDENCE_SCHEMA, SecurityProperty
from .linux_observer import collect


def inspect(configuration):
    profile = configuration["os_profile"]
    separate = (os.getuid() == os.geteuid() == profile["expected_uid"] != 0
                and os.getgid() == os.getegid() == profile["expected_gid"] != 0
                and os.getuid() != profile["backend_uid"])
    properties = {"process_identity": SecurityProperty(profile, separate, False,
                  "local observation only; no independent authority authenticated")}
    # UID difference is observable; account exclusivity still needs operator proof.
    for name, declared in {
        "account_exclusivity": "dedicated account, no backend supplementary groups",
        "privileges": "NoNewPrivileges, empty permitted/effective/bounding capabilities",
        "filesystem": "host read-only, backend inaccessible, only own work/tmp writable",
        "devices": "no GPU or Docker socket",
        "network": {"backend_url": configuration["backend_url"], "provider_network": False},
        "cpu": "CPUQuota=50%", "memory": "MemoryMax=128M, MemorySwapMax=0",
        "processes": "TasksMax=8", "temporary_directory": "PrivateTmp=yes",
        "runtime_and_group_stop": "RuntimeMaxSec=55s, KillMode=control-group, TimeoutStopSec=5s",
    }.items():
        properties[name] = SecurityProperty(declared, None, False, "NOT VERIFIED: requires authorized OS negative tests")
    observations = {"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups()}
    for label, path in (("process_status", "/proc/self/status"), ("cgroup_membership", "/proc/self/cgroup")):
        try:
            raw = Path(path).read_text()[:16384]
            if label == "process_status":
                raw = "\n".join(line for line in raw.splitlines() if line.split(":", 1)[0] in
                                {"Uid", "Gid", "Groups", "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb", "NoNewPrivs", "Seccomp"})
            observations[label] = raw
        except OSError:
            observations[label] = "NOT AVAILABLE"
    return {"schema": EVIDENCE_SCHEMA, "profile": profile["schema"], "status": "NOT VERIFIED",
            "properties": {name: prop.to_dict() for name, prop in properties.items()}, "observations": observations,
            "linux_evidence": collect(configuration), "authority": "not_authenticated"}


def require_isolation(configuration, *, verifier_fd=None):
    from .verification_channel import VerificationSession
    session = VerificationSession(configuration, verifier_fd)
    session.check()
    return session
