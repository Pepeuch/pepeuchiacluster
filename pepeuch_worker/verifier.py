"""One-shot diagnostic verifier. No service installation and no permit issuer.

The inherited root channel is prepared for an independent controller. This tool
only emits denial/NOT VERIFIED until actual independent OS tests are integrated.
"""

import argparse
import os
from pathlib import Path
import socket
import struct
import sys
import time

from control_plane.contracts import Problem, canonical, decode_json, fields
from .contracts import configuration
from .linux_observer import collect
from .private_io import configuration_input
from .verification import assess, digest, policy
from .verification_channel import MAX_FRAME, REPLY, REQUEST


def unit_metadata(unit):
    """Fixed read-only command, controller only; no worker subprocess or shell."""
    import re
    import subprocess
    if not isinstance(unit, str) or re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}\.service", unit) is None:
        raise Problem("invalid_unit_observation")
    names = ("Id", "MainPID", "ControlGroup", "InvocationID", "KillMode", "RuntimeMaxUSec", "TimeoutStopUSec")
    try:
        result = subprocess.run(["/usr/bin/systemctl", "show", "--no-pager", "--property=" + ",".join(names), "--", unit],
                                capture_output=True, timeout=1, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Problem("unit_observation_unavailable") from None
    if result.returncode != 0 or len(result.stdout) > 16384:
        raise Problem("unit_observation_unavailable")
    data = {}
    for line in result.stdout.decode("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in names or key in data:
            raise Problem("invalid_unit_observation")
        data[key] = value
    if set(data) != set(names):
        raise Problem("unit_observation_unavailable")
    return data


def receive_authenticated_request(sock):
    """Per-message credentials, not SO_PEERCRED captured when PID1 opened an FD."""
    credentials = None
    deadline = time.monotonic() + 2
    def receive(size):
        nonlocal credentials
        result = bytearray()
        while len(result) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Problem("verifier_request_refused")
            sock.settimeout(remaining)
            data, ancillary, flags, _ = sock.recvmsg(size - len(result), socket.CMSG_SPACE(struct.calcsize("3i")))
            found = []
            unexpected = False
            for level, kind, raw in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS and len(raw) == struct.calcsize("3i"):
                    found.append(struct.unpack("3i", raw))
                else:
                    unexpected = True
                    if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                        import array
                        descriptors = array.array("i")
                        descriptors.frombytes(raw[:len(raw) - len(raw) % descriptors.itemsize])
                        for fd in descriptors:
                            os.close(fd)
            if (not data or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or unexpected
                    or len(found) != 1 or credentials is not None and credentials != found[0]):
                raise Problem("verifier_request_refused")
            credentials = found[0]
            result.extend(data)
        return bytes(result)
    size = struct.unpack("!I", receive(4))[0]
    if not 0 < size <= MAX_FRAME:
        raise Problem("verifier_request_refused")
    return decode_json(receive(size)), credentials


def serve_diagnostic(sock, config, requested):
    """Prepared entry point only. Must be explicitly invoked in a future root pilot."""
    if os.geteuid() != 0:
        raise Problem("independent_root_controller_required")
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    # Bounded lifetime and number of rechecks; no permanent privileged service.
    deadline = time.monotonic() + 55
    for _ in range(8):
        if time.monotonic() >= deadline:
            break
        request, credentials = receive_authenticated_request(sock)
        fields(request, ("schema", "nonce", "configuration", "context"))
        pid, uid, gid = credentials
        if (request["schema"] != REQUEST or uid != config["os_profile"]["expected_uid"]
                or gid != config["os_profile"]["expected_gid"] or digest(request["configuration"]) != digest(config)
                or not isinstance(request["nonce"], str) or len(request["nonce"]) != 64):
            raise Problem("verifier_request_refused")
        actual = collect(config, pid=pid)
        if digest(actual["process"]) != digest(request["context"]):
            raise Problem("verifier_request_refused")
        try:
            actual["applied"]["systemd"] = unit_metadata(requested["unit"])
        except (Problem, OSError, ValueError):
            actual["unavailable"].append("unit_metadata")
        assessment = assess(config, requested, actual, now=time.monotonic())
        now = time.monotonic()
        response = {"schema": REPLY, "nonce": request["nonce"], "context_sha256": digest(actual["process"]),
                    "configuration_sha256": digest(config), "profile": requested["profile"], "policy_sha256": digest(requested),
                    "receipt_sha256": "0" * 64, "issued_monotonic": now, "expires_monotonic": now + 1,
                    "decision": "deny", "guarantees": assessment["guarantees"]}
        raw = canonical(response).encode()
        sock.settimeout(2)
        sock.sendall(struct.pack("!I", len(raw)) + raw)
        # A diagnostic denial ends the manual controller immediately.
        break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration-file", required=True, type=Path)
    parser.add_argument("--policy-file", required=True, type=Path, help="Requested policy; never itself an attestation")
    parser.add_argument("--pid", type=int, help="Read-only audit of a target process")
    parser.add_argument("--serve-fd", type=int, help="Already-open connected FD, never a listener")
    parser.add_argument("--authorized-disposable-pilot", action="store_true")
    args = parser.parse_args()
    try:
        # Reject privileged mode before reading operator paths or touching an FD.
        if args.serve_fd is not None and (not args.authorized_disposable_pilot or os.geteuid() != 0):
            raise Problem("independent_root_controller_required")
        config = configuration(decode_json(configuration_input(args.configuration_file)))
        requested = policy(decode_json(configuration_input(args.policy_file)))
        if args.serve_fd is None:
            result = assess(config, requested, collect(config, pid=args.pid), now=time.monotonic())
            print(canonical(result))
            return 2  # An audit report never activates the worker.
        if not 3 <= args.serve_fd <= 1024 or args.pid is not None:
            raise Problem("invalid_verifier_descriptor")
        with socket.socket(fileno=os.dup(args.serve_fd)) as sock:
            if sock.family != socket.AF_UNIX or sock.type != socket.SOCK_STREAM:
                raise Problem("invalid_verifier_descriptor")
            serve_diagnostic(sock, config, requested)
        return 2
    except (Problem, OSError, ValueError, TypeError):
        print("Vérification refusée : NOT VERIFIED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
