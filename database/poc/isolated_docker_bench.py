#!/usr/bin/env python3
"""Explicit VM150 synthetic bench; existing local images only, never deletes.

Execute only under the user's specific isolated-bench authorization. No service
installation, host configuration, historical POC exec, pull, prune, rm or GPU.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import subprocess
import threading
import time


IMAGES = {
    "postgresql": "sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab",
    "surrealdb": "sha256:649a60a3b9c0177d9923c938e1c2563e48cde2a9d06ac2c0519714be719b02af",
}
HISTORICAL = ("pepeuch-ai-poc-postgres-1", "pepeuch-ai-surreal-poc-surrealdb-1")
LABEL = "ai.pepeuch.synthetic-bench"
GiB = 1024**3
LIMITS = {"cpus": 2, "memory_bytes": 4*GiB, "pids": 256, "data_budget_bytes": 2*GiB,
          "campaign_budget_bytes": 6*GiB, "minimum_free_disk_bytes": 10*GiB,
          "minimum_available_memory_bytes": 8*GiB, "max_stage_models": 10000}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def command(args, *, data=None, timeout=60, check=True):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        # Never echo full Docker inspections, environment files or log streams.
        raise RuntimeError("Command failed: " + args[0] + " " + (args[1] if len(args)>1 else "") + " exit=" + str(result.returncode))
    return result


def docker(*args, **kwargs):
    return command(["docker", *args], **kwargs)


def inspect(kind, identity):
    return json.loads(docker(kind, "inspect", identity).stdout)[0]


def available_memory():
    values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    return int(values["MemAvailable"].split()[0])*1024


def historical_fingerprint():
    rows = []
    for name in HISTORICAL:
        item = json.loads(docker("inspect", "--type", "container", name).stdout)[0]
        rows.append({"name": name, "id": item["Id"], "image": item["Image"],
                     "state": {key: item["State"].get(key) for key in ("Status", "StartedAt", "FinishedAt", "ExitCode", "Restarting")},
                     "mounts": [{k: m.get(k) for k in ("Type", "Source", "Destination", "RW")} for m in item["Mounts"]]})
    return rows


def preflight(root):
    images = {}
    for engine, expected in IMAGES.items():
        image = inspect("image", expected)  # Exact ID, never a mutable tag.
        if image["Id"] != expected:
            raise ValueError("Local image identity mismatch")
        images[engine] = {"id": image["Id"], "repo_digests": image.get("RepoDigests", []),
                          "default_user": image.get("Config", {}).get("User", "")}
    free = shutil.disk_usage(root.parent).free
    memory = available_memory()
    history = historical_fingerprint()
    if any(row["state"]["Status"] != "exited" for row in history):
        raise ValueError("Historical POC state changed; refuse to continue")
    if free < 20*GiB or memory < 12*GiB or os.cpu_count() < 4 or os.getloadavg()[0] > os.cpu_count():
        raise ValueError("Insufficient free resources for the bounded campaign")
    return {"at": utc(), "images": images, "free_disk_bytes": free, "available_memory_bytes": memory,
            "cpus": os.cpu_count(), "load": os.getloadavg(), "limits": LIMITS, "historical": history}


def save(path, value):
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode()+b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def event(root, kind, **fields):
    row = {"at": utc(), "event": kind, **fields}
    # Only fixed public fields and synthetic measurements are passed by callers.
    with (root/"events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True)+"\n")
        stream.flush()
    print(json.dumps(row, sort_keys=True), flush=True)


def create_arguments(engine, root, campaign):
    data = root/(engine+"-data")
    args = ["create", "--pull=never", "--name", campaign+"-"+engine, "--label", LABEL+"="+campaign,
            "--network", campaign+"-net", "--cpus", "2", "--memory", "4g", "--memory-swap", "4g",
            "--pids-limit", "256", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--read-only", "--restart", "no", "--log-driver", "json-file", "--log-opt", "max-size=10m", "--log-opt", "max-file=2",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=268435456"]
    if engine == "postgresql":
        args += ["--user", "70:70", "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,noexec,size=16777216,uid=70,gid=70",
                 "--mount", "type=bind,src="+str(data)+",dst=/var/lib/postgresql/data",
                 "--env", "POSTGRES_USER=bench", "--env", "POSTGRES_DB=bench", "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
                 IMAGES[engine], "postgres", "-c", "shared_buffers=128MB", "-c", "work_mem=16MB", "-c", "max_connections=20",
                 "-c", "max_wal_size=256MB", "-c", "statement_timeout=30000"]
    elif engine == "surrealdb":
        args += ["--user", "1000:1000", "--mount", "type=bind,src="+str(data)+",dst=/data",
                 "--env-file", str(root/"surreal.private.env"),
                 "--env", "SURREAL_ROCKSDB_BLOCK_CACHE_SIZE=134217728", "--env", "SURREAL_ROCKSDB_WRITE_BUFFER_SIZE=33554432",
                 "--env", "SURREAL_ROCKSDB_MAX_WRITE_BUFFER_NUMBER=2",
                 IMAGES[engine], "start", "--bind", "0.0.0.0:8000", "rocksdb:/data/surreal.db"]
    else:
        raise ValueError("Closed engine selection required")
    return args


def create(root, campaign):
    if (root/"objects.json").exists():
        return json.loads((root/"objects.json").read_text())
    password = secrets.token_urlsafe(32)
    fd = os.open(root/"surreal.private.env", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("SURREAL_USER=benchadmin\nSURREAL_PASS="+password+"\n")
    for engine, uid in (("postgresql", 70), ("surrealdb", 1000)):
        directory = root/(engine+"-data")
        directory.mkdir(mode=0o700)
        os.chown(directory, uid, uid)
    network = docker("network", "create", "--internal", "--label", LABEL+"="+campaign, campaign+"-net").stdout.decode().strip()
    event(root, "network_created", identity=network)
    objects = {"campaign": campaign, "network": network, "containers": {}}
    for engine in IMAGES:
        identity = docker(*create_arguments(engine, root, campaign)).stdout.decode().strip()
        if re.fullmatch(r"[0-9a-f]{64}", identity) is None:
            raise ValueError("Unexpected created container identity")
        objects["containers"][engine] = identity
        event(root, "container_created", engine=engine, identity=identity)
    save(root/"objects.json", objects)
    return objects


def owned_metadata(objects, engine):
    identity = objects["containers"][engine]
    item = json.loads(docker("inspect", "--type", "container", identity).stdout)[0]
    campaign = objects["campaign"]
    if (item["Id"] != identity or item["Name"] != "/"+campaign+"-"+engine
            or item["Config"].get("Labels", {}).get(LABEL) != campaign or item["Image"] != IMAGES[engine]):
        raise ValueError("Container does not belong to this campaign")
    if (item["HostConfig"]["Privileged"] or item["HostConfig"].get("PortBindings")
            or item["HostConfig"]["NanoCpus"] != 2_000_000_000 or item["HostConfig"]["Memory"] != 4*GiB
            or item["HostConfig"].get("MemorySwap") != 4*GiB
            or item["HostConfig"]["PidsLimit"] != 256 or not item["HostConfig"]["ReadonlyRootfs"]
            or "no-new-privileges:true" not in item["HostConfig"].get("SecurityOpt", [])
            or item["HostConfig"].get("CapAdd") or "ALL" not in item["HostConfig"].get("CapDrop", [])
            or item["HostConfig"].get("Devices") or item["HostConfig"].get("DeviceRequests")
            or item["Config"].get("User") != ("70:70" if engine=="postgresql" else "1000:1000")):
        raise ValueError("Isolation or resource policy differs from the approved plan")
    network = inspect("network", objects["network"])
    if not network.get("Internal") or network.get("Labels", {}).get(LABEL) != campaign:
        raise ValueError("Private internal network required")
    data = [m for m in item["Mounts"] if m["Type"] == "bind"]
    expected = str(Path("/var/tmp")/campaign/(engine+"-data"))
    if len(data) != 1 or data[0]["Source"] != expected:
        raise ValueError("Only the new dedicated data directory may be mounted")
    for mount in item["Mounts"]:
        if mount["Type"] != "volume":
            continue
        # This exact Surreal image declares /logs as an anonymous VOLUME.
        # It is new, owned by this new container, retained and budgeted too.
        if engine != "surrealdb" or mount["Destination"] != "/logs" or re.fullmatch(r"[0-9a-f]{64}", mount.get("Name", "")) is None:
            raise ValueError("Unexpected ancillary volume")
        volume = inspect("volume", mount["Name"])
        if (volume["Mountpoint"] != mount["Source"]
                or volume.get("Driver") != "local"
                or datetime.fromisoformat(volume["CreatedAt"]).timestamp() < datetime.fromisoformat(item["Created"]).timestamp()-2):
            raise ValueError("Ancillary volume is not newly allocated for this container")
    return item


def stop(objects, root):
    errors = []
    for engine in objects["containers"]:
        try:
            item = owned_metadata(objects, engine)
            if item["State"]["Running"]:
                docker("stop", "--time", "15", item["Id"], timeout=45)
            try:
                event(root, "container_stopped", engine=engine, identity=item["Id"])
            except OSError:
                pass  # An artifact write failure must never prevent stopping.
        except Exception as exc:
            errors.append(engine+":"+type(exc).__name__)
    if errors:
        raise RuntimeError("Owned container stop failed: "+",".join(errors))


def disk_size(root):
    total = 0
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in files:
            total += (Path(directory)/name).lstat().st_size
    return total


class Monitor:
    def __init__(self, root, objects):
        self.root, self.objects = root, objects
        self.end = threading.Event()
        self.failed = None
        self.records = []
        self.started = time.time()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def sample(self):
        row = {"at": utc(), "host_available_memory_bytes": available_memory(),
               "host_free_disk_bytes": shutil.disk_usage(self.root).free, "campaign_bytes": disk_size(self.root),
               "host_load": os.getloadavg(), "containers": {}}
        if (row["host_available_memory_bytes"] < LIMITS["minimum_available_memory_bytes"]
                or row["host_free_disk_bytes"] < LIMITS["minimum_free_disk_bytes"]
                or row["campaign_bytes"] > LIMITS["campaign_budget_bytes"] or row["host_load"][0] > os.cpu_count()*2):
            raise RuntimeError("Host resource guard tripped")
        for engine in self.objects["containers"]:
            item = owned_metadata(self.objects, engine)
            if not item["State"]["Running"] or item["State"].get("OOMKilled"):
                raise RuntimeError("Unexpected container exit or OOM")
            pid = item["State"]["Pid"]
            raw = Path(f"/proc/{pid}/cgroup").read_text().strip()
            if not raw.startswith("0::/") or "\n" in raw:
                raise RuntimeError("Unified cgroup v2 required")
            group = (Path("/sys/fs/cgroup")/raw[4:]).resolve()
            if not group.is_relative_to("/sys/fs/cgroup"):
                raise RuntimeError("Unexpected cgroup path")
            stat = dict(x.split() for x in (group/"cpu.stat").read_text().splitlines())
            events = dict(x.split() for x in (group/"memory.events").read_text().splitlines())
            memory = int((group/"memory.current").read_text())
            pids = int((group/"pids.current").read_text())
            ancillary = {m["Destination"]: {"source": m["Source"], "bytes": disk_size(Path(m["Source"]))}
                         for m in item["Mounts"] if m["Type"] == "volume"}
            size = disk_size(self.root/(engine+"-data")) + sum(m["bytes"] for m in ancillary.values())
            stats = {"cpu_seconds": int(stat["usage_usec"])/1e6, "memory_current_bytes": memory,
                     "memory_peak_bytes": int((group/"memory.peak").read_text()), "pids": pids, "data_bytes": size,
                     "oom_kill": int(events.get("oom_kill", 0)), "ancillary_volumes": ancillary}
            row["containers"][engine] = stats
            if memory > 3.5*GiB or pids >= 224 or size > LIMITS["data_budget_bytes"] or stats["oom_kill"]:
                raise RuntimeError("Container resource guard tripped")
        row["campaign_bytes"] += sum(m["bytes"] for c in row["containers"].values() for m in c["ancillary_volumes"].values())
        if row["campaign_bytes"] > LIMITS["campaign_budget_bytes"]:
            raise RuntimeError("Campaign disk budget including ancillary storage exceeded")
        journal = command(["journalctl", "-k", "--since", "@"+str(int(self.started)), "-p", "err", "-o", "json", "--no-pager"], timeout=10)
        count = 0
        for line in journal.stdout.decode(errors="replace").splitlines():
            message = str(json.loads(line).get("MESSAGE", ""))
            count += bool(re.search(r"hardware error|I/O error|machine check|out of memory|oom-kill", message, re.I))
        row["new_kernel_hardware_or_oom_error_count"] = count
        if count:
            raise RuntimeError("New kernel hardware or memory error detected")
        self.records.append(row)
        return row

    def loop(self):
        while not self.end.wait(2):
            try:
                self.sample()
            except Exception as exc:
                self.failed = type(exc).__name__ + ": " + str(exc)[:160]
                try:
                    stop(self.objects, self.root)
                finally:
                    return

    def check(self):
        if self.failed:
            raise RuntimeError("Resource monitor stopped the campaign: " + self.failed)

    def close(self):
        self.end.set()
        self.thread.join(timeout=30)


def host_address(item, network_name):
    raw = item["NetworkSettings"]["Networks"][network_name]["IPAddress"]
    if not ipaddress.ip_address(raw).is_private:
        raise ValueError("Private internal address required")
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Explicit isolated-bench authorization required")
    parser.add_argument("--qualification-only", action="store_true",
                        help="Only synthetic B2 replay/restore qualification; no performance campaign")
    args = parser.parse_args()
    root = args.root
    if (root.parent != Path("/var/tmp") or not re.fullmatch(r"pepeuch-dbbench-[a-z0-9-]{12,64}", root.name)
            or root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077):
        parser.error("Existing dedicated private /var/tmp campaign directory required")
    if os.geteuid() != 0:
        parser.error("VM administrator must run the explicitly authorized Docker bench")
    def interrupted(signum, frame):
        raise InterruptedError("Controller interrupted by signal "+str(signum))
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    before = preflight(root)
    if not args.execute:
        print(json.dumps(before, sort_keys=True))
        return 0
    attempt = root/("attempt-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+secrets.token_hex(3))
    attempt.mkdir(mode=0o700)
    save(attempt/"preflight.json", before)
    objects, monitor, outcome = None, None, {"status": "FAILED", "data_kind": "synthetic", "started_at": utc()}
    try:
        objects = create(root, root.name)
        for engine in objects["containers"]:
            item = owned_metadata(objects, engine)
            if item["State"]["Running"]:
                raise ValueError("Campaign containers unexpectedly already running")
            docker("start", item["Id"])
        from isolated_bench_runtime import run
        monitor = Monitor(root, objects)
        monitor.sample()
        monitor.thread.start()
        outcome.update(run(root, attempt, objects, monitor, qualification_only=args.qualification_only))
        monitor.check()
        outcome["status"] = "VERIFIED"
    except BaseException as exc:
        # No headers, credential values, environment, raw logs or traceback.
        outcome["error"] = {"type": type(exc).__name__, "detail": str(exc)[:320]}
        event(root, "attempt_failed", error_type=type(exc).__name__, detail=str(exc)[:240])
    finally:
        if monitor is not None:
            monitor.close()
        if objects is not None:
            try:
                stop(objects, root)
                outcome["final_container_states"] = {e: owned_metadata(objects,e)["State"]["Status"] for e in objects["containers"]}
            except Exception as exc:
                outcome.update(status="FAILED", stop_error=type(exc).__name__)
        if monitor is not None:
            save(attempt/"resource_samples.json", {"samples": monitor.records, "failure": monitor.failed})
        after = historical_fingerprint()
        outcome["historical_metadata_unchanged"] = after == before["historical"]
        if not outcome["historical_metadata_unchanged"]:
            outcome["status"] = "FAILED"
        outcome["finished_at"] = utc()
        save(attempt/"result.json", outcome)
        event(root, "attempt_finished", status=outcome["status"], artifacts=str(attempt), historical_metadata_unchanged=outcome["historical_metadata_unchanged"])
    return 0 if outcome["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
