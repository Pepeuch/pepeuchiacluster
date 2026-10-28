"""Offline Proxmox plan and validation. No qm, network, key reads or provisioning."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


def build_plan(environment):
    def value(name, default):
        raw = environment.get(name, default)
        if not isinstance(raw, str) or not raw or len(raw) > 2048 or any(ord(c) < 32 for c in raw):
            raise ValueError("Invalid public configuration")
        return raw
    def integer(name, default, low, high):
        raw = value(name, default)
        if re.fullmatch(r"[1-9][0-9]{0,8}", raw) is None or not low <= int(raw) <= high:
            raise ValueError("Invalid resource limit")
        return int(raw)
    def path(name, default):
        raw = value(name, default)
        if not raw.startswith("/") or ".." in PurePosixPath(raw).parts or str(PurePosixPath(raw)) != raw:
            raise ValueError("Canonical absolute path required")
        return raw
    vmid = integer("VMID", "9200", 100, 999999999)
    if vmid == 150:
        raise ValueError("VM150 is protected")
    name = value("VMNAME", "pepeuch-ai")
    user = value("CI_USER", "pepeuch")
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", name) is None or re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user) is None:
        raise ValueError("Invalid hostname or account")
    storage = value("STORAGE", "local-lvm")
    snippets = value("SNIPPET_STORAGE", "local")
    bridge = value("BRIDGE", "vmbr0")
    for item in (storage, snippets, bridge):
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", item) is None:
            raise ValueError("Invalid infrastructure identifier")
    release = value("DEBIAN_RELEASE", "13")
    if re.fullmatch(r"[0-9]{1,2}", release) is None:
        raise ValueError("Invalid release")
    url = value("IMAGE_URL", "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2")
    if re.fullmatch(r"https://[A-Za-z0-9.-]+/[A-Za-z0-9._/-]+", url) is None:
        raise ValueError("Public HTTPS image URL required, no credentials or query")
    checksum = environment.get("IMAGE_SHA256") or None
    if checksum is not None and (not isinstance(checksum, str) or re.fullmatch(r"[0-9a-f]{64}", checksum) is None):
        raise ValueError("Invalid image checksum")
    directory = path("SNIPPET_DIR", "/var/lib/vz/snippets")
    return {"schema": "pepeuch.infrastructure/vm-plan/v1", "status": "PARTIAL", "executed": False,
            "vmid": vmid, "name": name, "protected_vmids": [150], "ci_admin_user": user,
            "resources": {"memory_mb": integer("MEMORY_MB", "24576", 1024, 1048576),
                          "cores": integer("CORES", "8", 1, 256), "disk_gb": integer("DISK_GB", "80", 8, 4096)},
            "storage": storage, "snippet_storage": snippets, "bridge": bridge,
            "image": {"url": url, "file": path("IMAGE_FILE", f"/var/lib/vz/template/iso/debian-{release}-genericcloud-amd64.qcow2"),
                      "sha256_expected": checksum},
            "snippet": directory + "/" + name + "-user-data.yaml",
            "public_key_file": path("SSH_KEY_FILE", "/root/.ssh/authorized_keys"),
            "effects_if_applied": ["new_vm_q35_ovmf", "cloud_image_import", "new_cloudinit_snippet", "cloudinit_admin_sudo_and_docker",
                                   "guest_packages_upgrade", "guest_docker_install", "guest_directories_and_sysctl"],
            "not_verified": ["hypervisor_access", "free_vmid_and_capacity", "storage_and_snippets_mapping", "image_and_guest_boot",
                             "guest_network_and_cloudinit", "backup_and_restore"],
            "gpu_passthrough": False, "starts_vm": False, "automatic_rollback": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-paths", action="store_true", help="Read-only metadata checks; never create or repair paths")
    args = parser.parse_args()
    try:
        plan = build_plan(os.environ)
        if args.check_paths:
            check_paths(plan)
        if not args.check and not args.check_paths:
            print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError):
        print("VM plan refused: invalid configuration or protected VM150", file=sys.stderr)
        return 2


def check_paths(plan):
    """Reject symbolic/untrusted existing components before AND after mkdir.

    This is a host-admin script, not a sandbox against another malicious root.
    Shared writable non-sticky parents are deliberately unsupported.
    """
    targets = [Path(plan["image"]["file"]), Path(plan["snippet"])]
    for target in targets:
        for parent in reversed(target.parents):
            try:
                info = parent.lstat()
            except FileNotFoundError:
                break
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                    or info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
                raise ValueError("Untrusted output directory")
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o022):
            raise ValueError("Untrusted output file")


if __name__ == "__main__":
    raise SystemExit(main())
