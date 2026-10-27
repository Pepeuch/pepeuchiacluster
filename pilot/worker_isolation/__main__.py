"""Manual disposable-VM bench. No installation, service activation or firewall I/O."""

import argparse
import hashlib
import os
from pathlib import Path
import stat
import sys
import time

from control_plane.contracts import Problem, canonical, decode_json
from pepeuch_worker.linux_observer import bounded, collect
from pepeuch_worker.private_io import configuration_input, opened_directory
from .probes import CASES, FILES, connect, deny_open, device_metadata, scope, require_lifecycle_limits


def synthetic(case, run_id):
    return ("PEPEUCH B531 SYNTHETIC " + case + " " + run_id + "\n").encode()


def protected_scope(path):
    """Root-owned immutable scope; it authorizes test targets, never an OS permit."""
    path = Path(path)
    import re
    if re.fullmatch(r"/(?:opt|var/lib)/pepeuch-b531-fixtures-[0-9a-f]{32}/PILOT_SCOPE\.json", str(path)) is None:
        raise Problem("operator_scope_required")
    with opened_directory(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o444:
                raise Problem("operator_scope_required")
            raw = os.read(fd, 8193)
            if len(raw) > 8192:
                raise Problem("operator_scope_required")
        finally:
            os.close(fd)
    data = scope(decode_json(raw))
    if path != Path(data["fixture_root"]) / "PILOT_SCOPE.json":
        raise Problem("operator_scope_required")
    root_info = Path(data["fixture_root"]).lstat()
    if root_info.st_uid != 0 or stat.S_IMODE(root_info.st_mode) & 0o022:
        raise Problem("operator_scope_required")
    if (data["boot_id"] != bounded("/proc/sys/kernel/random/boot_id", 128).strip()
            or not data["created_monotonic"] <= time.monotonic() < data["expires_monotonic"]):
        raise Problem("pilot_scope_expired")
    return data


def prepare(data):
    """Explicit future root operation: new synthetic directory only, no cleanup."""
    if os.geteuid() != 0:
        raise Problem("authorized_root_pilot_required")
    data = scope(data)
    root = Path(data["fixture_root"])
    with opened_directory(root.parent) as parent:
        os.mkdir(root.name, 0o755, dir_fd=parent)  # Existing destinations are refused.
    with opened_directory(root) as directory:
        os.fchmod(directory, 0o755)
    for folder, mode in (("backend", 0o700), ("backend/secrets", 0o700), ("backend/app", 0o700), ("backend/workspaces", 0o700), ("published", 0o755)):
        (root / folder).mkdir(mode=mode)
        with opened_directory(root / folder) as directory:
            os.fchmod(directory, mode)
    for case, name in FILES.items():
        path = root / name
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, synthetic(case, data["run_id"]))
            os.fchmod(fd, 0o666 if case == "outside_write" else 0o644 if case == "results_preserved" else 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
    marker = root / "PILOT_SCOPE.json"
    fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o444)
    try:
        os.write(fd, canonical(data).encode())
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "prepare", "probe", "child-wait"))
    parser.add_argument("--scope-file", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--authorized-disposable-pilot", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            data = scope(decode_json(configuration_input(args.scope_file)))
            print(canonical({"schema": "pepeuch.worker/pilot-plan/v1", "scope": data, "cases": list(CASES), "executed": False}))
            return 0
        if not args.authorized_disposable_pilot:
            raise Problem("explicit_disposable_pilot_required")
        if args.command == "prepare":
            if os.geteuid() != 0:
                raise Problem("authorized_root_pilot_required")
            prepare(decode_json(configuration_input(args.scope_file)))
            print("Synthetic fixture prepared. OS: NOT VERIFIED.")
            return 0
        data = protected_scope(args.scope_file)
        if os.getuid() != data["expected_uid"] or os.getgid() != data["expected_gid"] or os.geteuid() == 0:
            raise Problem("pilot_worker_identity_required")
        if args.command == "child-wait":
            time.sleep(8)
            return 0
        case = args.case
        if case is None:
            raise Problem("explicit_fixed_case_required")
        if case in FILES and case != "results_preserved":
            result = deny_open(Path(data["fixture_root"]) / FILES[case], writing=case == "outside_write")
        elif case in ("backend_connect", "other_loopback", "controlled_peer", "ipv6"):
            result = connect(data, case)
        elif case in ("gpu", "docker"):
            result = device_metadata()
        elif case == "results_preserved":
            raw = configuration_input(Path(data["fixture_root"]) / FILES[case])
            expected = hashlib.sha256(synthetic(case, data["run_id"])).hexdigest()
            result = {"outcome": "candidate_preserved" if hashlib.sha256(raw).hexdigest() == expected else "FAIL", "sha256": hashlib.sha256(raw).hexdigest()}
        elif case == "resources":
            # No memory allocation loop, CPU load or PID stress is performed.
            result = {"outcome": "NOT VERIFIED", "subject": "pilot scope, not a worker identity", "observations": collect(data)}
        else:
            # Separate, explicit lifecycle probes: at most ONE fixed child, no prompt.
            import subprocess
            require_lifecycle_limits(collect(data))
            child = None
            try:
                if case == "child_stop":
                    child = subprocess.Popen([sys.executable, "-E", "-s", "-B", "-m", "pilot.worker_isolation", "child-wait",
                                              "--scope-file", str(args.scope_file), "--authorized-disposable-pilot"], close_fds=True)
                print(canonical({"schema": "pepeuch.worker/pilot-lifecycle/v1", "case": case, "pid": os.getpid(),
                                 "child_pid": None if child is None else child.pid, "outcome": "NOT VERIFIED"}), flush=True)
                time.sleep(10 if child is not None else 60)
                result = {"outcome": "NOT VERIFIED", "detail": "external_lifecycle_observer_required"}
            finally:
                if child is not None:
                    if child.poll() is None:
                        child.terminate()
                    try:
                        child.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=1)
        print(canonical({"schema": "pepeuch.worker/isolation-probe/v1", "run_id": data["run_id"], "case": case,
                         "pid": os.getpid(), "verified": False, "result": result}))
        return 2  # A probe output is never itself a strict authorization.
    except (Problem, OSError, ValueError):
        print("Sonde refusée : NOT VERIFIED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
