#!/usr/bin/env python3
"""Read-only Docker metadata inventory. No exec, logs, probes or environment dump."""

import json
import re
import subprocess
import sys


SERVICES = (("pepeuch-ai-poc", "postgres", "/var/lib/postgresql/data", "volume"),
            ("pepeuch-ai-surreal-poc", "surrealdb", "/data", "bind"))
# Deliberately exclude Env, healthcheck Output, command lines and labels.
FORMAT = ('{"id":{{json .Id}},"image":{{json .Config.Image}},'
          '"state":{{json .State.Status}},"restart_count":{{json .RestartCount}},'
          '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},'
          '"mounts":[{{range $i,$m := .Mounts}}{{if $i}},{{end}}'
          '{"type":{{json $m.Type}},"destination":{{json $m.Destination}},'
          '"source":{{json $m.Source}},"rw":{{json $m.RW}}}{{end}}]}')


def docker(arguments):
    result = subprocess.run(["docker", *arguments], capture_output=True, timeout=15, check=False)
    if result.returncode or len(result.stdout) > 1_000_000:
        raise ValueError("Docker metadata unavailable")
    return result.stdout.decode("utf-8", errors="strict")


def inspect(run=docker):
    services = []
    for project, service, destination, mount_type in SERVICES:
        row = {"project": project, "service": service, "status": "NOT VERIFIED",
               "reason": "container_missing", "container": None}
        try:
            raw = run(["ps", "-aq", "--no-trunc", "--filter", "label=com.docker.compose.project=" + project,
                       "--filter", "label=com.docker.compose.service=" + service])
            ids = raw.splitlines()
            if not ids:
                services.append(row)
                continue
            if len(ids) != 1 or re.fullmatch(r"[0-9a-f]{64}", ids[0]) is None:
                raise ValueError("Ambiguous service identity")
            data = json.loads(run(["inspect", "--type", "container", "--format", FORMAT, ids[0]]))
            if not isinstance(data, dict) or set(data) != {"id", "image", "state", "restart_count", "health", "mounts"}:
                raise ValueError("Invalid metadata shape")
            if (data["id"] != ids[0] or data["state"] not in {"created", "running", "paused", "restarting", "removing", "exited", "dead"}
                    or data["health"] not in {None, "starting", "healthy", "unhealthy"}
                    or type(data["restart_count"]) is not int or data["restart_count"] < 0
                    or not isinstance(data["image"], str) or len(data["image"]) > 256
                    or not isinstance(data["mounts"], list)):
                raise ValueError("Invalid container metadata")
            mounts = []
            for mount in data["mounts"]:
                if (not isinstance(mount, dict) or set(mount) != {"type", "destination", "source", "rw"}
                        or mount["type"] not in {"bind", "volume", "tmpfs", "npipe", "cluster"}
                        or any(not isinstance(mount[k], str) or len(mount[k]) > 4096 for k in ("source", "destination"))
                        or type(mount["rw"]) is not bool):
                    raise ValueError("Invalid mount metadata")
                if mount["destination"] == destination:
                    mounts.append(mount)
            # Report only the expected data mount, never secret/config mounts.
            data["mounts"] = mounts
            valid_mount = len(mounts) == 1 and mounts[0]["type"] == mount_type and mounts[0]["rw"]
            ready = data["state"] == "running" and data["health"] == "healthy" and valid_mount
            row.update(status="VERIFIED" if ready else "PARTIAL",
                       reason="metadata_only" if ready else "state_health_or_mount_unconfirmed", container=data)
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            # Never include exception text, stderr, credentials or provider output.
            row.update(reason="metadata_unavailable_or_invalid")
        services.append(row)
    return {"format": "pepeuch-ai.poc-health-inventory/v1", "read_only": True,
            "scope": "docker_metadata_only", "services": services,
            "not_verified": ["query_access", "data_integrity", "restart_persistence", "backup_restore", "load_stability"]}


def main():
    report = inspect()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if all(s["status"] == "VERIFIED" for s in report["services"]) else 1


if __name__ == "__main__":
    sys.exit(main())
